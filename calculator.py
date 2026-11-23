"""필라테스 회원권 만료일·환불금액 계산 코어.

UI와 분리된 순수 파이썬 모듈이라 unittest로 전수 검증한다.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

# ---------------------------------------------------------------------------
# 기준 값
# ---------------------------------------------------------------------------

PENALTY_RATE = 0.10  # 위약금 10%
GROUP_PER_SESSION = 22_000  # 6:1 그룹 회당 차감액
PERSONAL_PER_SESSION = 77_000  # 1:1 개인 회당 차감액

WEEKDAY_KO = ("월", "화", "수", "목", "금", "토", "일")
UNIT_KO = {"months": "개월", "weeks": "주"}


@dataclass(frozen=True)
class Preset:
    """회원권 프리셋 한 건."""

    id: str
    kind: str  # "group" | "personal"
    sessions: int
    period_value: int
    period_unit: str  # "months" | "weeks"
    price: int

    @property
    def per_session(self) -> int:
        return GROUP_PER_SESSION if self.kind == "group" else PERSONAL_PER_SESSION

    @property
    def kind_label(self) -> str:
        return "6:1 그룹" if self.kind == "group" else "1:1 개인"

    @property
    def period_label(self) -> str:
        return f"{self.period_value}{UNIT_KO[self.period_unit]}"

    @property
    def label(self) -> str:
        return f"{self.kind_label} {self.sessions}회"


PRESETS: tuple[Preset, ...] = (
    Preset("g12", "group", 12, 2, "months", 264_000),
    Preset("g24", "group", 24, 3, "months", 381_800),
    Preset("g36", "group", 36, 4, "months", 500_700),
    Preset("g48", "group", 48, 6, "months", 571_600),
    Preset("p15", "personal", 15, 10, "weeks", 750_000),
    Preset("p20", "personal", 20, 10, "weeks", 1_200_000),
    Preset("p30", "personal", 30, 20, "weeks", 1_500_000),
)

PRESETS_BY_ID = {p.id: p for p in PRESETS}


class CalcError(ValueError):
    """입력값이 계산 조건을 만족하지 않을 때."""


# ---------------------------------------------------------------------------
# 만료일
# ---------------------------------------------------------------------------


def add_months(base: date, months: int) -> date:
    """월을 더하되 대상 월의 말일을 넘지 않게 보정한다."""
    total = base.month - 1 + months
    year = base.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(base.day, last_day))


def calculate_expiry(start: date, value: int, unit: str) -> date:
    """시작일 포함 기준 만료일.

    - N개월: 시작일 + N개월(말일 보정) - 1일
    - N주  : 시작일 + (N * 7 - 1)일
    """
    if unit not in ("months", "weeks"):
        raise CalcError("기간 단위는 개월 또는 주여야 합니다.")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise CalcError("기간은 1 이상의 정수여야 합니다.")
    if unit == "months":
        return add_months(start, value) - timedelta(days=1)
    return start + timedelta(days=value * 7 - 1)


def total_days(start: date, expiry: date) -> int:
    """시작일과 만료일을 모두 포함한 이용일수."""
    return (expiry - start).days + 1


def weekday_ko(d: date) -> str:
    return WEEKDAY_KO[d.weekday()]


def format_date_ko(d: date) -> str:
    return f"{d.isoformat()}({weekday_ko(d)})"


def format_won(amount: int) -> str:
    return f"{amount:,}원"


# ---------------------------------------------------------------------------
# 환불금액
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RefundResult:
    paid: int
    penalty: int
    usage_deduction: int
    refund: int
    refundable: bool
    remaining_sessions: int | None


def calculate_refund(
    paid: int,
    used: int,
    per_session: int,
    sessions: int | None = None,
) -> RefundResult:
    """환불금액 = 결제금액 - 위약금(10%) - (사용횟수 x 회당 차감액).

    위약금의 원 미만은 절사한다. 결과가 0원 미만이면 0원, 환불 불가.
    """
    if isinstance(paid, bool) or not isinstance(paid, int):
        raise CalcError("결제금액은 숫자여야 합니다.")
    if paid < 0:
        raise CalcError("결제금액은 0원 이상이어야 합니다.")
    if isinstance(used, bool) or not isinstance(used, int):
        raise CalcError("사용 횟수는 숫자여야 합니다.")
    if used < 0:
        raise CalcError("사용 횟수는 0회 이상이어야 합니다.")
    if isinstance(per_session, bool) or not isinstance(per_session, int) or per_session < 0:
        raise CalcError("회당 차감액이 올바르지 않습니다.")
    if sessions is not None:
        if isinstance(sessions, bool) or not isinstance(sessions, int) or sessions < 1:
            raise CalcError("총 횟수는 1회 이상이어야 합니다.")
        if used > sessions:
            raise CalcError(f"사용 횟수가 총 횟수({sessions}회)를 초과했습니다.")

    penalty = int(
        (Decimal(paid) * Decimal(str(PENALTY_RATE))).to_integral_value(rounding=ROUND_FLOOR)
    )
    deduction = used * per_session
    raw = paid - penalty - deduction
    refund = raw if raw > 0 else 0
    remaining = None if sessions is None else sessions - used
    return RefundResult(
        paid=paid,
        penalty=penalty,
        usage_deduction=deduction,
        refund=refund,
        refundable=raw > 0,
        remaining_sessions=remaining,
    )


# ---------------------------------------------------------------------------
# 입력 파싱 도우미 (UI/서버에서 공통 사용)
# ---------------------------------------------------------------------------


def parse_amount(raw) -> int:
    """'264,000원' 같은 문자열을 정수로. 빈 값은 CalcError."""
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    if raw is None:
        raise CalcError("금액을 입력해 주세요.")
    text = str(raw).replace(",", "").replace("원", "").replace(" ", "").strip()
    if text == "":
        raise CalcError("금액을 입력해 주세요.")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise CalcError("금액은 숫자로 입력해 주세요.") from None
    if value != value.to_integral_value():
        raise CalcError("금액은 원 단위 정수로 입력해 주세요.")
    return int(value)


def parse_int(raw, field: str = "값") -> int:
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    text = "" if raw is None else str(raw).replace(",", "").replace(" ", "").strip()
    if text == "":
        raise CalcError(f"{field}을(를) 입력해 주세요.")
    try:
        value = int(text)
    except ValueError:
        raise CalcError(f"{field}은(는) 숫자로 입력해 주세요.") from None
    return value


def parse_date(raw) -> date:
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    text = "" if raw is None else str(raw).strip()
    if text == "":
        raise CalcError("시작일을 선택해 주세요.")
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise CalcError("시작일 형식이 올바르지 않습니다.")


# ---------------------------------------------------------------------------
# 화면용 결과 묶음
# ---------------------------------------------------------------------------


def build_expiry_result(start_raw, value_raw, unit: str, label: str = "") -> dict:
    start = parse_date(start_raw)
    value = parse_int(value_raw, "기간")
    expiry = calculate_expiry(start, value, unit)
    days = total_days(start, expiry)
    period = f"{value}{UNIT_KO[unit]}"

    lines = []
    if label:
        lines.append(f"[{label}]")
    lines.append(f"시작일 {format_date_ko(start)}")
    lines.append(f"만료일 {format_date_ko(expiry)}")
    lines.append(f"이용 기간 총 {days}일")
    guide = "\n".join(lines)

    return {
        "ok": True,
        "start": start.isoformat(),
        "start_text": format_date_ko(start),
        "expiry": expiry.isoformat(),
        "expiry_text": format_date_ko(expiry),
        "expiry_weekday": weekday_ko(expiry),
        "total_days": days,
        "period_text": period,
        "guide_text": guide,
    }


def build_refund_result(
    paid_raw,
    used_raw,
    per_session_raw,
    sessions_raw=None,
    label: str = "",
) -> dict:
    paid = parse_amount(paid_raw)
    if paid <= 0:
        raise CalcError("결제금액은 0원보다 커야 합니다.")
    used = parse_int(used_raw, "사용 횟수")
    per_session = parse_int(per_session_raw, "회당 차감액")
    sessions = None if sessions_raw in (None, "") else parse_int(sessions_raw, "총 횟수")

    result = calculate_refund(paid, used, per_session, sessions)

    refund_text = format_won(result.refund)
    if not result.refundable:
        refund_text = "0원 (환불 불가)"

    lines = []
    if label:
        lines.append(f"[환불 내역] {label}")
    else:
        lines.append("[환불 내역]")
    lines.append(f"결제금액 {format_won(result.paid)}")
    lines.append(f"위약금(10%) {format_won(result.penalty)}")
    lines.append(f"사용 차감 {used}회 × {format_won(per_session)} = {format_won(result.usage_deduction)}")
    lines.append(f"최종 환불금액 {refund_text}")

    return {
        "ok": True,
        "paid": result.paid,
        "paid_text": format_won(result.paid),
        "penalty": result.penalty,
        "penalty_text": format_won(result.penalty),
        "used": used,
        "per_session": per_session,
        "per_session_text": format_won(per_session),
        "usage_deduction": result.usage_deduction,
        "usage_text": format_won(result.usage_deduction),
        "usage_detail": f"{used}회 × {format_won(per_session)}",
        "refund": result.refund,
        "refund_text": refund_text,
        "refundable": result.refundable,
        "remaining_sessions": result.remaining_sessions,
        "receipt_text": "\n".join(lines),
    }
