"""Pydantic 请求/响应模型。"""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventIn(BaseModel):
    box_code: str = Field(..., min_length=1, max_length=64, description="周转箱箱号")
    seq: int = Field(..., ge=0, description="该箱递增的事件序号，从 0 开始")
    temperature: float = Field(..., ge=-100, le=100, description="摄氏温度")
    event_time: datetime = Field(..., description="ISO 8601，建议带时区，如 2026-09-23T10:00:00+08:00")

    @field_validator("box_code")
    @classmethod
    def _strip_box_code(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("box_code 不能为空")
        return v

    @field_validator("event_time")
    @classmethod
    def _to_utc(cls, v: datetime) -> datetime:
        # 无时区信息按 UTC 处理；有时区则换算为 UTC 后去掉 tzinfo 落库
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc).replace(tzinfo=None)
        return v.astimezone(timezone.utc).replace(tzinfo=None)


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    box_code: str
    seq: int
    temperature: float
    event_time: datetime
    created_at: datetime


class EventAck(BaseModel):
    status: str = Field(..., description="accepted=首次入库，duplicate=重复上报（幂等忽略）")
    event: EventOut


class BoxState(BaseModel):
    box_code: str
    seq: int
    temperature: float
    event_time: datetime


class BoxListItem(BaseModel):
    box_code: str


class MerkleProofStep(BaseModel):
    sibling_hash: str = Field(
        ..., description="该层兄弟节点哈希（小写十六进制 SHA-256）"
    )
    side: Literal["left", "right"] = Field(
        ...,
        description=(
            "兄弟节点相对目标节点的方向：left=兄弟在左，"
            "调用方重算时计算 hash(node||sibling)；right=兄弟在右，计算 hash(sibling||node)"
        ),
    )


class MerkleProofResult(BaseModel):
    box_code: str = Field(..., description="周转箱箱号")
    seq_from: int = Field(..., description="查询起始序号（含）")
    seq_to: int = Field(..., description="查询结束序号（含）")
    target_seq: int = Field(..., description="被证明事件的序号")
    event_count: int = Field(
        ..., description="区间内实际已存事件条数（缺号不补点）"
    )
    root_hash: str = Field(
        ..., description="区间事件按 seq 升序构造的 Merkle 树根哈希（小写十六进制）"
    )
    target_leaf_hash: str = Field(
        ..., description="目标事件的叶子哈希（小写十六进制）"
    )
    proof: list[MerkleProofStep] = Field(
        ...,
        description=(
            "逐层兄弟哈希与左右方向（由叶向根）；单事件证明为空路径，"
            "此时根哈希即目标叶哈希"
        ),
    )


class ClockAuditItem(BaseModel):
    seq: int = Field(..., description="事件序号")
    original_time: datetime = Field(..., description="原始 UTC 事件时间（不改动原始记录）")
    suggested_time: datetime = Field(..., description="保序回归后的建议 UTC 时间")
    offset_micros: int = Field(
        ..., description="建议时间 - 原时间（微秒，正为向前修正，负为回拨修正）"
    )
    block_seq_from: int = Field(..., description="该事件所属合并块的起始序号")
    block_seq_to: int = Field(..., description="该事件所属合并块的结束序号")


class TrajectoryCompressionPoint(BaseModel):
    seq: int = Field(..., description="保留事件的原始序号")
    event_time: datetime = Field(..., description="保留事件的原始 UTC 事件时间")
    temperature: float = Field(..., description="保留事件的原始温度（℃）")


class TrajectoryCompressionResult(BaseModel):
    box_code: str = Field(..., description="周转箱箱号")
    seq_from: int = Field(..., description="查询起始序号（含）")
    seq_to: int = Field(..., description="查询结束序号（含）")
    max_error: float = Field(..., description="允许的最大重建误差（℃），非负有限")
    event_count: int = Field(..., description="区间内事件条数")
    kept_count: int = Field(
        ..., description="保留事件数（满足误差约束的最少值；同数量时保留序号序列字典序最小）"
    )
    omitted_count: int = Field(..., description="被省略事件数（event_count - kept_count）")
    actual_max_error: float | None = Field(
        ...,
        description=(
            "被省略事件的重建温度与原值之差的最大绝对值（℃）；"
            "无被省略事件时为 0.0，区间内无事件时为 null"
        ),
    )
    kept_events: list[TrajectoryCompressionPoint] = Field(
        ..., description="保留事件（按序号升序），原始记录不被改动"
    )


class HeatExposureSegment(BaseModel):
    start_seq: int = Field(..., description="段起点事件序号")
    end_seq: int = Field(..., description="段终点事件序号")
    start_time: datetime = Field(..., description="段起点校正后 UTC 时间（等权保序回归）")
    end_time: datetime = Field(..., description="段终点校正后 UTC 时间（等权保序回归）")
    gap_seconds: float = Field(..., description="校正后段时长（秒）")
    start_temperature: float = Field(..., description="段起点温度（℃）")
    end_temperature: float = Field(..., description="段终点温度（℃）")
    celsius_seconds: float = Field(..., description="该段超过上限部分的精确积分（℃·秒）")


class HeatExposureResult(BaseModel):
    box_code: str = Field(..., description="周转箱箱号")
    seq_from: int = Field(..., description="查询起始序号（含）")
    seq_to: int = Field(..., description="查询结束序号（含）")
    upper_limit: float = Field(..., description="温度上限（℃）")
    max_gap_seconds: float = Field(..., description="允许计入的最大段时长（秒）")
    event_count: int = Field(..., description="区间内事件条数")
    segment_count: int = Field(..., description="计入积分的段数")
    skipped_segment_count: int = Field(
        ..., description="因校正后间隔为零或超过 max_gap_seconds 而未计入的段数"
    )
    total_celsius_seconds: float = Field(..., description="各段积分合计（℃·秒）")
    segments: list[HeatExposureSegment] = Field(..., description="计入积分的逐段明细")


class TemperatureMedianResult(BaseModel):
    box_code: str = Field(..., description="周转箱箱号")
    seq_from: int = Field(..., description="查询起始序号（含）")
    seq_to: int = Field(..., description="查询结束序号（含）")
    max_gap_seconds: float = Field(..., description="允许计入的最大段时长（秒）")
    event_count: int = Field(..., description="区间内事件条数")
    segment_count: int = Field(
        ..., description="计入分布的有效段数（校正后时长大于 0 且不超过 max_gap_seconds）"
    )
    skipped_segment_count: int = Field(
        ..., description="因校正后间隔为零或超过 max_gap_seconds 而未计入的段数"
    )
    total_seconds: float = Field(..., description="各有效段校正后时长合计（秒）")
    median_temperature: float | None = Field(
        ...,
        description=(
            "时间加权温度中位数（℃）：累计时长占比首次达到一半的最低温度；"
            "无有效段时为 null"
        ),
    )
