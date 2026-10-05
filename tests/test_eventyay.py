import json

import pytest

from vcut.eventyay import (
    ScheduleError,
    conference_info,
    parse_event_url,
    parse_sessions,
    schedule_url,
)

PAYLOAD = {
    "schedule": {
        "url": "https://wikimedia.eventyay.com/wikicon/india26/schedule/",
        "conference": {
            "title": "WikiConference India 2026",
            "acronym": "india26",
            "start": "2026-09-04",
            "time_zone_name": "Asia/Kolkata",
            "days": [
                {
                    "date": "2026-09-04",
                    "rooms": {
                        "Grand Ballroom": [
                            {
                                "code": "FWLP9F",
                                "title": "Address by the Board",
                                "abstract": "An address.",
                                "description": "",
                                "date": "2026-09-04T09:10:00+05:30",
                                "room": "Grand Ballroom",
                                "track": "Others",
                                "language": "en",
                                "url": "https://example.org/talk/FWLP9F/",
                                "do_not_record": False,
                                "persons": [{"public_name": "Ravi Kumar"}],
                            },
                            {
                                # Registration slots carry no talk code.
                                "id": 36785,
                                "title": {"en": "Registrations"},
                                "persons": [],
                            },
                        ]
                    },
                }
            ],
        },
    }
}


@pytest.mark.parametrize(
    "value",
    [
        "india26",
        "wikicon/india26",
        "https://wikimedia.eventyay.com/wikicon/india26/",
        "https://wikimedia.eventyay.com/wikicon/india26/schedule/",
        "https://wikimedia.eventyay.com/wikicon/india26/talk/FWLP9F/",
    ],
)
def test_event_url_forms_all_resolve_to_the_same_event(value):
    base, organiser, event = parse_event_url(value)
    assert event == "india26"
    assert organiser == "wikicon"
    assert base == "https://wikimedia.eventyay.com"


def test_a_different_host_and_organiser_are_honoured():
    base, organiser, event = parse_event_url("https://pretalx.com/wm/wikimania2026/schedule/")
    assert (base, organiser, event) == ("https://pretalx.com", "wm", "wikimania2026")


def test_an_empty_event_is_an_error():
    with pytest.raises(ScheduleError):
        parse_event_url("")


def test_schedule_url_points_at_the_pretalx_export():
    url = schedule_url("https://wikimedia.eventyay.com", "wikicon", "india26")
    assert url.endswith("/wikicon/india26/schedule/export/schedule.json")


def test_sessions_are_indexed_by_talk_code():
    sessions = parse_sessions(PAYLOAD)
    assert set(sessions) == {"FWLP9F"}
    assert sessions["FWLP9F"].title == "Address by the Board"


def test_entries_without_a_code_are_ignored():
    # Breaks and registration desks are not talks and have no metadata to fetch.
    assert "Registrations" not in {s.title for s in parse_sessions(PAYLOAD).values()}


def test_speakers_become_the_author_string():
    assert parse_sessions(PAYLOAD)["FWLP9F"].author == "Ravi Kumar"


def test_session_day_is_taken_from_the_schedule_day():
    assert parse_sessions(PAYLOAD)["FWLP9F"].day == "2026-09-04"


def test_lookup_is_case_insensitive():
    sessions = parse_sessions(PAYLOAD)
    assert "FWLP9F" in sessions
    assert sessions.get("fwlp9f".upper()) is not None


def test_conference_info_is_extracted():
    info = conference_info(PAYLOAD)
    assert info["title"] == "WikiConference India 2026"
    assert info["timezone"] == "Asia/Kolkata"


def test_localised_title_dictionaries_are_flattened():
    payload = json.loads(json.dumps(PAYLOAD))
    talk = payload["schedule"]["conference"]["days"][0]["rooms"]["Grand Ballroom"][0]
    talk["title"] = {"en": "Localised Title"}
    assert parse_sessions(payload)["FWLP9F"].title == "Localised Title"


def test_an_empty_payload_yields_no_sessions():
    assert parse_sessions({}) == {}


def test_full_description_joins_abstract_and_description():
    payload = json.loads(json.dumps(PAYLOAD))
    talk = payload["schedule"]["conference"]["days"][0]["rooms"]["Grand Ballroom"][0]
    talk["description"] = "Extra detail."
    session = parse_sessions(payload)["FWLP9F"]
    assert session.full_description == "An address.\n\nExtra detail."


def test_cached_schedule_is_used_when_offline(tmp_path, monkeypatch):
    import vcut.eventyay as module

    monkeypatch.setattr(module, "_cache_dir", lambda: tmp_path)
    cache = module._cache_path("wikicon", "india26")
    cache.write_text(json.dumps(PAYLOAD), encoding="utf-8")
    fetched = module.fetch_schedule("india26", offline=True)
    assert conference_info(fetched)["acronym"] == "india26"


def test_offline_without_a_cache_is_an_error(tmp_path, monkeypatch):
    import vcut.eventyay as module

    monkeypatch.setattr(module, "_cache_dir", lambda: tmp_path)
    with pytest.raises(ScheduleError, match="offline"):
        module.fetch_schedule("nosuchevent", offline=True)


def test_a_stale_cache_is_served_when_the_network_fails(tmp_path, monkeypatch):
    import httpx

    import vcut.eventyay as module

    monkeypatch.setattr(module, "_cache_dir", lambda: tmp_path)
    module._cache_path("wikicon", "india26").write_text(json.dumps(PAYLOAD), encoding="utf-8")

    def explode(*args, **kwargs):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(module.httpx, "get", explode)
    # cache_ttl=0 forces a refresh attempt, which fails and falls back.
    fetched = module.fetch_schedule("india26", cache_ttl=0)
    assert conference_info(fetched)["acronym"] == "india26"
