from __future__ import annotations

APPLICATION_STATUSES = ("new", "in_review", "contacted", "accepted", "rejected")
LEGACY_APPLICATION_STATUSES = ("in_progress", "closed")
ALL_APPLICATION_STATUSES = frozenset((*APPLICATION_STATUSES, *LEGACY_APPLICATION_STATUSES))

_LABELS = {
    "uz": {
        "new": "Yangi",
        "in_review": "Ko‘rib chiqilmoqda",
        "contacted": "Bog‘lanildi",
        "accepted": "Qabul qilindi",
        "rejected": "Rad etildi",
        "in_progress": "Ko‘rib chiqilmoqda",
        "closed": "Yopildi (eski holat)",
    },
    "ru": {
        "new": "Новая",
        "in_review": "На рассмотрении",
        "contacted": "Связались",
        "accepted": "Принята",
        "rejected": "Отклонена",
        "in_progress": "На рассмотрении",
        "closed": "Закрыта (старый статус)",
    },
    "en": {
        "new": "New",
        "in_review": "In review",
        "contacted": "Contacted",
        "accepted": "Accepted",
        "rejected": "Rejected",
        "in_progress": "In review",
        "closed": "Closed (legacy)",
    },
}


def application_status_label(status: str, language: str = "uz") -> str:
    labels = _LABELS.get(language, _LABELS["uz"])
    return labels.get(status, status)

