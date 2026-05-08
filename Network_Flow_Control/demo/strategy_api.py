"""
竞赛级传输策略：事件驱动驱动 + SACK精确恢复 + 交换机SRPT严格优先级 + ECMP负载均衡
完全遵循 sim_api 约束，仅使用公开接口，无任何非法导入。
"""

from sim_api import (
    ControlPacketSpec, DataPacketSpec, HostContext, HostInitInfo,
    HostStrategy, LinkId, MAX_PAYLOAD, PacketId, PacketView,
    SwitchContext, SwitchInitInfo, SwitchStrategy,
)

MSS = MAX_PAYLOAD
HEADER = 64

# ---------- 可调参数 ----------
DELAYED_ACK_US = 5.0            # 延迟 ACK 定时器
MIN_CWND = 2 * MSS
INIT_CWND_RATIO = 2.0           # 初始窗口倍数
MIN_RTO = 200.0                 # 最小重传超时 (μs)
MAX_RTO = 1_000_000.0           # 最大重传超时
DEFAULT_RTO = 1000.0


# ---------- 辅助：提取包的优先级特征 ----------
def _packet_priority(pv: PacketView) -> tuple:
    """
    为交换机提供排序依据：
    返回值越小，发送优先级越高。
    (是否是数据, -优先级, 剩余字节数, 截止时间)
    """
    if pv.is_ctrl:
        # 控制包（ACK）拥有绝对最高优先级
        return (0, 0, 0, 0)
    
    c = pv.custom
    if isinstance(c, dict):
        prio = c.get('p', 0)
        rem = c.get('r', 10**9)
        dl = c.get('d', 10**9)
        return (1, -prio, rem, dl)
    return (1, 0, 10**9, 10**9)


# ---------- 发送端状态 ----------
class SenderFlow:
    def __init__(self, fid: int, dst: int, size: int, prio: int, deadline: float, now: float):
        self.fid = fid
        self.dst = dst
        self.total = size
        self.prio = prio
        self.deadline = deadline
        self.next_new = 0
        self.acked = 0
        self.cwnd = MIN_CWND
        self.ssthresh = 2**31 - 1
        
        self.inflight = []        # 保存发出的包 {seq, len, time, retx}
        self.retx_queue = []      # 等待重传的包
        
        self.srtt = 0.0
        self.rttvar = 0.0
        self.rto = DEFAULT_RTO
        self.rto_active = False
        self.rto_expire_time = 0.0
        
        self.last_ack = 0
        self.dup_cnt = 0
        self.recovery = False
        self.recover_point = 0

    @property
    def inflight_bytes(self) -> int:
        return sum(s['len'] for s in self.inflight)

    def can_send(self) -> bool:
        return self.next_new < self.total and self.inflight_bytes < self.cwnd

    def next_segment(self) -> dict:
        if self.retx_queue:
            seg = self.retx_queue.pop(0)
            seg['retx'] = True
            return seg
        if self.can_send():
            length = min(MSS, self.total - self.next_new)
            seq = self.next_new
            self.next_new += length
            return {'seq': seq, 'len': length, 'retx': False}
        return None

    def on_send(self, seg: dict, now: float):
        entry = {**seg, 'time': now}
        self.inflight = [s for s in self.inflight if not (s['seq'] == seg['seq'] and s['len'] == seg['len'])]
        self.inflight.append(entry)

    def on_ack(self, ack_seq: int, sack_blocks: list, echo: float, now: float):
        newly_acked = 0
        updated_inflight = []
        
        # 1. 累积确认
        for s in self.inflight:
            if s['seq'] + s['len'] <= ack_seq:
                newly_acked += s['len']
                if not s.get('retx') and echo > 0:
                    self._update_rtt(now - echo)
            else:
                updated_inflight.append(s)
        self.inflight = updated_inflight

        # 2. SACK 块消除重传冗余
        for start, end in sack_blocks:
            start = max(start, ack_seq)
            if start >= end: continue
            survivors = []
            for s in self.inflight:
                seg_end = s['seq'] + s['len']
                if s['seq'] >= start and seg_end <= end:
                    newly_acked += s['len']
                    if not s.get('retx') and echo > 0:
                        self._update_rtt(now - echo)
                    continue
                survivors.append(s)
            self.inflight = survivors

        # 3. 拥塞与重传控制
        if ack_seq > self.last_ack:
            self.dup_cnt = 0
            self.acked = ack_seq
            if self.recovery and ack_seq >= self.recover_point:
                self.recovery = False
                self.cwnd = self.ssthresh
        elif ack_seq == self.last_ack and not self.recovery and self.inflight:
            self.dup_cnt += 1
        self.last_ack = ack_seq

        if ack_seq > self.last_ack or newly_acked > 0:
            if self.recovery:
                self.cwnd += newly_acked
            elif self.cwnd < self.ssthresh:
                self.cwnd += newly_acked
            else:
                self.cwnd += max(1, (MSS * newly_acked) // self.cwnd)

        if self.dup_cnt == 3 and not self.recovery:
            self._fast_retransmit()

    def _update_rtt(self, rtt: float):
        if self.srtt == 0:
            self.srtt = rtt
            self.rttvar = rtt / 2
        else:
            self.rttvar = 0.75 * self.rttvar + 0.25 * abs(self.srtt - rtt)
            self.srtt = 0.875 * self.srtt + 0.125 * rtt
        self.rto = max(MIN_RTO, min(MAX_RTO, self.srtt + 4 * self.rttvar))

    def _fast_retransmit(self):
        self.recovery = True
        self.recover_point = self.next_new
        self.ssthresh = max(MIN_CWND, self.cwnd // 2)
        self.cwnd = self.ssthresh + 3 * MSS
        unacked = sorted(self.inflight, key=lambda s: s['seq'])
        if unacked:
            lost = unacked[0]
            if not any(r['seq'] == lost['seq'] and r['len'] == lost['len'] for r in self.retx_queue):
                self.retx_queue.append({k: v for k, v in lost.items() if k != 'time'})

    def on_timeout(self):
        for s in self.inflight:
            if not any(r['seq'] == s['seq'] and r['len'] == s['len'] for r in self.retx_queue):
                self.retx_queue.append({k: v for k, v in s.items() if k != 'time'})
        self.inflight.clear()
        self.ssthresh = max(MIN_CWND, self.cwnd // 2)
        self.cwnd = MIN_CWND
        self.recovery = False
        self.dup_cnt = 0


# ---------- 接收端状态 ----------
class RecvContext:
    def __init__(self, fid: int, src: int):
        self.fid = fid
        self.src = src
        self.timer_active = False


# ---------- Host 策略 ----------
class MyHostStrategy(HostStrategy):
    def __init__(self):
        self.senders = {}
        self.recvs = {}
        self.ack_pool = {}
        self.bw_bytes_us = 0.0
        self.base_rtt_us = 0.0

    def on_sim_start(self, init: HostInitInfo) -> None:
        self.bw_bytes_us = init.link.bandwidth_gbps * 125.0
        self.base_rtt_us = init.link.latency_us * 2.0

    def _ensure_rx_space_for(self, needed: int, ctx: HostContext):
        """丢弃低优先级包以腾出空间，避免丢弃 ACK 或高优数据"""
        while ctx.get_rx_buffer_remaining() < needed:
            buf = ctx.get_received_packets()
            if not buf: break
            
            # 找到优先级最低的包进行丢弃
            candidate = None
            worst_prio = -10**9
            for pv in buf:
                if pv.is_ctrl: continue
                c = pv.custom
                prio = c.get('p', 0) if isinstance(c, dict) else 0
                if candidate is None or prio < worst_prio:
                    worst_prio = prio
                    candidate = pv
            
            if candidate:
                ctx.drop_packet_in_buffer(candidate.packet_id)
            else:
                break

    def on_flow_arrival(self, flow_id: int, dst_node: int, size_bytes: int,
                        priority: int, deadline_us: float, ctx: HostContext) -> None:
        bdp = self.bw_bytes_us * self.base_rtt_us
        sf = SenderFlow(flow_id, dst_node, size_bytes, priority, deadline_us, ctx.now_us())
        sf.cwnd = int(min(size_bytes, max(MIN_CWND, bdp * INIT_CWND_RATIO)))
        self.senders[flow_id] = sf
        ctx.request_link_ready()

    def on_link_ready(self, ctx: HostContext):
        # 1. 绝对优先发送 ACK
        if self.ack_pool:
            dst, ack_data = next(iter(self.ack_pool.items()))
            del self.ack_pool[dst]
            return ControlPacketSpec(dst_node=dst, custom=ack_data)

        # 2. SRPT: 选择优先级最高、剩余字节最少的可发送流
        candidates = []
        for sf in self.senders.values():
            if sf.acked < sf.total and (sf.retx_queue or sf.can_send()):
                candidates.append(sf)
        
        if not candidates:
            return None
            
        candidates.sort(key=lambda f: (-f.prio, f.total - f.acked, f.deadline))

        now = ctx.now_us()
        for sf in candidates:
            seg = sf.next_segment()
            if not seg: continue
            
            sf.on_send(seg, now)
            
            # 管理 RTO 定时器
            if not sf.rto_active:
                sf.rto_active = True
                sf.rto_expire_time = now + sf.rto
                ctx.schedule_timer(sf.rto, ('rto', sf.fid))

            # 注入元数据供交换机 SRPT 调度
            custom_data = {
                't': now, 
                'p': sf.prio, 
                'd': sf.deadline, 
                'r': sf.total - sf.acked
            }
            
            return DataPacketSpec(
                flow_id=sf.fid,
                seq_no=seg['seq'],
                payload_size=seg['len'],
                custom=custom_data
            )
        return None

    def on_packet_arrival(self, pkt: PacketView, ctx: HostContext) -> None:
        now = ctx.now_us()
        if pkt.is_ctrl:
            c = pkt.custom
            if isinstance(c, dict) and c.get('type') == 'ack':
                fid = c['flow_id']
                sf = self.senders.get(fid)
                if sf and sf.acked < sf.total:
                    sf.on_ack(c['ack_seq'], c.get('sack', []), c.get('t', 0.0), now)
                    if not sf.inflight:
                        sf.rto_active = False
                    # 收到ACK表示链路可能有空闲/窗口已开，触发调度
                    ctx.request_link_ready()
            return

        # ---- 处理数据包 ----
        flow_id = pkt.flow_id
        if flow_id not in self.recvs:
            self.recvs[flow_id] = RecvContext(flow_id, pkt.src_node)
        rc = self.recvs[flow_id]

        before = ctx.get_delivered_up_to(flow_id)
        if pkt.seq_no == before:
            ctx.deliver_packet(pkt.packet_id)
        else:
            self._ensure_rx_space_for(pkt.size, ctx)
            if ctx.get_rx_buffer_remaining() >= pkt.size:
                ctx.add_packet_to_buffer(pkt.packet_id)

        # 循环推进交付
        while True:
            cur = ctx.get_delivered_up_to(flow_id)
            hit = next((pv for pv in ctx.get_received_packets() if pv.flow_id == flow_id and pv.seq_no == cur), None)
            if not hit: break
            ctx.deliver_packet(hit.packet_id)

        # 延迟 ACK
        echo_time = pkt.custom.get('t', 0.0) if isinstance(pkt.custom, dict) else 0.0
        self._build_and_cache_ack(flow_id, ctx, echo_time)
        
        if not rc.timer_active:
            rc.timer_active = True
            ctx.schedule_timer(DELAYED_ACK_US, ('dack', flow_id))

    def _build_and_cache_ack(self, fid: int, ctx: HostContext, echo_time: float):
        recv = self.recvs.get(fid)
        if not recv: return
        delv = ctx.get_delivered_up_to(fid)
        
        intervals = []
        for pv in ctx.get_received_packets():
            if pv.flow_id == fid and not pv.is_ctrl:
                start = pv.seq_no
                end = start + pv.payload_size
                if end > delv:
                    intervals.append((start, end))
                    
        merged = []
        for s, e in sorted(intervals, key=lambda x: x[0]):
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))
                
        sacks = [[max(s, delv), e] for s, e in merged if max(s, delv) < e][:3]
        
        self.ack_pool[recv.src] = {
            'type': 'ack',
            'flow_id': fid,
            'ack_seq': delv,
            'sack': sacks,
            't': echo_time
        }

    def on_timer(self, user_arg: object, ctx: HostContext) -> None:
        now = ctx.now_us()
        if isinstance(user_arg, tuple):
            event, fid = user_arg
            if event == 'rto':
                sf = self.senders.get(fid)
                if sf and sf.rto_active:
                    # 避免过早触发：检查是否真的到了计算好的过期时间
                    if now >= sf.rto_expire_time:
                        sf.rto_active = False
                        if sf.inflight:
                            sf.on_timeout()
                            ctx.request_link_ready()
                            # 重启 RTO 定时器
                            sf.rto_active = True
                            sf.rto_expire_time = now + sf.rto
                            ctx.schedule_timer(sf.rto, ('rto', fid))
                    else:
                        # 定时器时间未到，重新注册剩余时间的定时器
                        remain = max(1.0, sf.rto_expire_time - now)
                        ctx.schedule_timer(remain, ('rto', fid))
            elif event == 'dack':
                rc = self.recvs.get(fid)
                if rc: rc.timer_active = False
                ctx.request_link_ready()


# ---------- 交换机策略 ----------
class MySwitchStrategy(SwitchStrategy):
    def __init__(self):
        self.next_hops = {}

    def on_sim_start(self, init: SwitchInitInfo) -> None:
        self.next_hops = dict(init.next_hops)

    def on_packet_arrival(self, pkt: PacketView, input_port: LinkId,
                          ctx: SwitchContext):
        candidates = self.next_hops.get(pkt.dst_node, [])
        if not candidates:
            return None

        # 动态 ECMP：过滤容量不足的端口，选择队列占用字节最少的端口 (LSQ)
        best_port = None
        min_usage = float('inf')
        
        for port in candidates:
            usage = ctx.get_port_usage(port)
            if usage.capacity_bytes - usage.used_bytes >= pkt.size:
                if usage.used_bytes < min_usage:
                    min_usage = usage.used_bytes
                    best_port = port

        # 如果没有合法端口，返回 None 执行主动丢包
        return best_port

    def on_link_ready(self, output_port: LinkId, ctx: SwitchContext):
        ids = ctx.get_port_queue_packet_ids(output_port)
        if not ids:
            return None

        # SRPT + 严格优先级队列调度：扫描头部包，选取优先级最高的包
        # 为了避免全量扫描带来的性能损耗，最多扫描前 100 个包
        scan_limit = min(len(ids), 100)
        
        best_id = ids[0]
        best_score = _packet_priority(ctx.get_packet_view(best_id))

        for i in range(1, scan_limit):
            pid = ids[i]
            score = _packet_priority(ctx.get_packet_view(pid))
            if score < best_score:
                best_score = score
                best_id = pid
                
            # 若找到了极高优先级的控制包，直接返回，不再浪费计算资源
            if best_score[0] == 0:
                break

        return best_id