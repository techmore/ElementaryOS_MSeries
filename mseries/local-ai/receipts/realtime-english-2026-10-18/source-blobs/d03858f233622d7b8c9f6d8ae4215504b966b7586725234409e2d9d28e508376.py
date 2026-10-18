"""Explicit, review-only translation then grammar using the same local model."""
from dataclasses import dataclass
from dictation_review import ReviewUnavailable


@dataclass(frozen=True)
class Result:
    proposal: str
    translation: str | None = None
    warning: str | None = None


def transform(source, mode, language, reviewer):
    if mode in ('grammar', 'translate'):
        return Result(reviewer(source, mode, language))
    if mode != 'translate-polish':
        raise ReviewUnavailable('Choose a supported review mode')
    translation = reviewer(source, 'translate', language)
    try:
        polished = reviewer(translation, 'grammar', language)
    except ReviewUnavailable:
        return Result(translation, translation,
            'Translation retained. Grammar review is unavailable; original text is unchanged.')
    return Result(polished, translation)
