"""Chat list , search highlighting and day-grouping helpers."""

import re
import calendar
import datetime
import html as html_lib

import core

CHAT_LIST_FIELDS = (
    "id", "title", "category", "tags", "created", "updated",
    "messages_found", "message_snippets",
)

def project_chat(chat, extra_fields=()):
    projected = {key: chat.get(key) for key in CHAT_LIST_FIELDS if key in chat}
    for key in extra_fields:
        if key in chat:
            projected[key] = chat[key]
    return projected

def highlight_query(text, query):
    """html-escaped text with case-insensitive query matches wrapped in <strong>"""
    if text is None:
        return None
    escaped_text = html_lib.escape(str(text), quote=True)
    if not query:
        return escaped_text

    # cap the candidate list so a long query can't build a pathological
    # regex that gets re-run per result
    candidates = ([str(query).strip()] + core.search.normalize_words(query))[:12]
    pattern = "|".join(dict.fromkeys(
        re.escape(html_lib.escape(c, quote=True)) for c in candidates if c
    ))
    if not pattern:
        return escaped_text
    return re.sub(
        f"({pattern})",
        lambda m: '<strong class="search-highlight">' + m.group(1) + "</strong>",
        escaped_text,
        flags=re.IGNORECASE,
    )

def day_label_from_key(key, tz_offset_min=0):
    """human-readable label for a day/week/month group key (see group_key)"""
    if not key:
        return "Undated"
    if key.startswith("last-week"):
        return "Last Week"

    parts = key.split("-")
    try:
        year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2]) if len(parts) > 2 else 1
        date = datetime.date(year, month, day)
    except (ValueError, IndexError):
        return "Undated"

    # month group keys are 'YYYY-MM': always show the year, month groups
    # can span years and 'September' alone gets ambiguous
    if len(parts) == 2:
        return f"{calendar.month_name[month]} {year}"

    today = (datetime.datetime.utcnow() - datetime.timedelta(minutes=tz_offset_min)).date()
    diff_days = (today - date).days

    if diff_days == 0:
        return "Today"
    if diff_days == 1:
        return "Yesterday"
    if 1 < diff_days < 7:
        return date.strftime("%A")
    if date.year == today.year:
        return f"{calendar.month_name[month]} {day}"
    return f"{calendar.month_name[month]} {day}, {year}"

def chats_for_category(channel, category, tags=None):
    """get all chats in a category"""
    all_chats = channel.context.chat.get_all()
    if category:
        all_chats = [c for c in all_chats if c.get("category") == category]

    if tags:
        all_chats = [
            c for c in all_chats
            if all(t in (c.get("tags") or []) for t in tags)
        ]

    return all_chats

def local_day(updated_str, tz_offset_min):
    # naive UTC isoformat -> local date string 'YYYY-MM-DD'
    if not updated_str:
        return ""

    try:
        dt = datetime.datetime.fromisoformat(updated_str)
    except ValueError:
        return ""

    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)

    dt = dt - datetime.timedelta(minutes=tz_offset_min)
    return dt.date().isoformat()


def local_today(tz_offset_min):
    return (datetime.datetime.utcnow() - datetime.timedelta(minutes=tz_offset_min)).date()


# sidebar grouping tiers:
# - this week (Mon..today): one group per day ('YYYY-MM-DD')
# - last week (Mon..Sun):   one group, key 'last-week-<monday>'
# - older:                  one group per month ('YYYY-MM')
def group_key(updated_str, tz_offset_min):
    day = local_day(updated_str, tz_offset_min)
    if not day:
        return ""

    today = local_today(tz_offset_min)
    this_monday = today - datetime.timedelta(days=today.weekday())
    last_monday = this_monday - datetime.timedelta(days=7)

    if day >= this_monday.isoformat():
        return day
    if day >= last_monday.isoformat():
        return f"last-week-{last_monday.isoformat()}"
    return day[:7]
