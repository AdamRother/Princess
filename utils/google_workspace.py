"""Google Sheets, Drive, and Docs clients with OAuth flow and 'auto' resource creation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build as gdiscovery_build

BASE_DIR = Path(__file__).parent.parent
TOKEN_PATH = BASE_DIR / "config" / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]

# ── Tab headers ────────────────────────────────────────────────────────────────

TOPICS_HEADERS = [
    "⭐", "Idea", "Proof", "Search demand",
    "Why it works", "Keywords", "Score", "Status",
]

_VARIANTS_SUBHEADER = [
    "", "VARIANT TITLE", "ANGLE", "WHAT'S MODIFIED",
    "WHY THIS ANGLE WORKS BETTER", "", "", "",
]

VARIANTS_HEADERS = [
    "Topic #", "Topic Idea", "Angle", "Variant Title",
    "What's Modified", "Why This Angle Works Better",
]

DETAILS_HEADERS = [
    "Topic #", "Idea", "Source channel", "Source title", "Source URL",
    "Views/day", "Engagement %", "Autocomplete keywords", "Related searches",
    "Publish date", "Duration (s)", "Channel tier", "Primary competitor",
    "Source tags", "Description excerpt", "Run timestamp",
]

COMPETITORS_HEADERS = [
    "Rank", "Channel", "Subs", "Tier", "Composite score",
    "Uploads/month", "Median views", "Recent median", "Trajectory",
    "Engagement %", "Top breakout 1", "Top breakout 2", "Top breakout 3",
    "Last refreshed", "Notes",
]

CLUSTERS_HEADERS = [
    "Cluster #", "Core Topic", "Proven Views", "Source Channel",
    "Type", "Angle", "Your Title", "Target Keyword",
    "Why It Works", "Priority", "Status",
]

# ── Formatting colors ──────────────────────────────────────────────────────────

# Top 3 topic rows: warm yellow tint
_TOP3_BG = {"red": 1.0, "green": 0.97, "blue": 0.82}

# Variant sub-header rows: light gray
_SUBHEADER_BG = {"red": 0.93, "green": 0.93, "blue": 0.93}

# Angle badge background colors (white text)
_ANGLE_COLORS = {
    "Story-led":          {"red": 0.25, "green": 0.47, "blue": 0.85},
    "Confessional":       {"red": 0.61, "green": 0.15, "blue": 0.69},
    "Framework":          {"red": 0.09, "green": 0.57, "blue": 0.75},
    "Contrarian":         {"red": 0.86, "green": 0.21, "blue": 0.18},
    "Numbers":            {"red": 0.00, "green": 0.59, "blue": 0.53},
    "Question":           {"red": 0.13, "green": 0.39, "blue": 0.78},
    "Beginner-angle":     {"red": 0.24, "green": 0.65, "blue": 0.35},
    "Advanced-angle":     {"red": 0.08, "green": 0.28, "blue": 0.62},
    "Reframe":            {"red": 0.90, "green": 0.49, "blue": 0.13},
    "Behind-the-scenes":  {"red": 0.33, "green": 0.33, "blue": 0.33},
}

_WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}
_DARK  = {"red": 0.20, "green": 0.20, "blue": 0.20}
_BLUE  = {"red": 0.07, "green": 0.36, "blue": 0.93}

# Row stride: 1 main + 1 variant sub-header + 10 variants = 12 rows per topic
_STRIDE = 12


# ── Auth helpers ───────────────────────────────────────────────────────────────

def _get_creds(client_secrets_path: str) -> Credentials:
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())
    return creds


def get_sheets_client(client_secrets_path: str) -> gspread.Client:
    creds = _get_creds(client_secrets_path)
    return gspread.authorize(creds)


def get_drive_service(client_secrets_path: str):
    creds = _get_creds(client_secrets_path)
    return gdiscovery_build("drive", "v3", credentials=creds)


def get_docs_service(client_secrets_path: str):
    creds = _get_creds(client_secrets_path)
    return gdiscovery_build("docs", "v1", credentials=creds)


def _get_sheets_service(gc: gspread.Client):
    """Build raw Sheets API v4 service from gspread client credentials."""
    return gdiscovery_build("sheets", "v4", credentials=gc.http_client.auth)


# ── Sheet / folder helpers ─────────────────────────────────────────────────────

def ensure_sheet(
    gc: gspread.Client,
    sheet_id: str,
    title: str = "Sales YT — Topic Research",
) -> gspread.Spreadsheet:
    if sheet_id != "auto":
        return gc.open_by_key(sheet_id)
    print(f"  [sheets] Creating new spreadsheet: '{title}'...")
    spreadsheet = gc.create(title)
    new_id = spreadsheet.id
    print(f"  [sheets] Created: https://docs.google.com/spreadsheets/d/{new_id}")
    from utils.config import update_secret
    update_secret("target_sheet_id", new_id)
    return spreadsheet


def ensure_docs_folder(drive_service, folder_id: str, folder_name: str = "Sales YT — Scripts") -> str:
    if folder_id != "auto":
        return folder_id
    print(f"  [drive] Creating Drive folder: '{folder_name}'...")
    folder = drive_service.files().create(
        body={"name": folder_name, "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()
    new_id = folder["id"]
    print(f"  [drive] Created: https://drive.google.com/drive/folders/{new_id}")
    from utils.config import update_secret
    update_secret("target_docs_folder_id", new_id)
    return new_id


def _ensure_tab(spreadsheet: gspread.Spreadsheet, title: str) -> gspread.Worksheet:
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=2000, cols=26)


def delete_tab_if_exists(
    spreadsheet: gspread.Spreadsheet,
    gc: gspread.Client,
    title: str,
) -> None:
    try:
        ws = spreadsheet.worksheet(title)
        sheets_svc = _get_sheets_service(gc)
        sheets_svc.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet.id,
            body={"requests": [{"deleteSheet": {"sheetId": ws.id}}]},
        ).execute()
        print(f"  Removed legacy tab: '{title}'")
    except gspread.WorksheetNotFound:
        pass


# ── Formatting utilities ───────────────────────────────────────────────────────

def _utf16_len(s: str) -> int:
    """Count UTF-16 code units (emoji outside BMP count as 2)."""
    return sum(2 if ord(c) > 0xFFFF else 1 for c in s)


def _clean_sheet_state(sheets_svc, spreadsheet_id: str, sheet_id: int) -> None:
    """Delete existing row groups and conditional format rules for a tab."""
    sp_info = sheets_svc.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties.sheetId,rowGroups,conditionalFormats)",
    ).execute()
    requests = []
    for sh in sp_info.get("sheets", []):
        if sh["properties"]["sheetId"] != sheet_id:
            continue
        for grp in sh.get("rowGroups", []):
            requests.append({"deleteDimensionGroup": {"range": grp["range"]}})
        rules = sh.get("conditionalFormats", [])
        for idx in range(len(rules) - 1, -1, -1):
            requests.append({"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": idx}})
    if requests:
        sheets_svc.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests}
        ).execute()


def _repeat_cell_bg(sheet_id: int, row: int, col_start: int, col_end: int, color: dict) -> dict:
    return {
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": row, "endRowIndex": row + 1,
                      "startColumnIndex": col_start, "endColumnIndex": col_end},
            "cell": {"userEnteredFormat": {"backgroundColor": color}},
            "fields": "userEnteredFormat.backgroundColor",
        }
    }


def _repeat_cell_wrap(sheet_id: int, row_start: int, row_end: int, col: int) -> dict:
    return {
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": row_start, "endRowIndex": row_end,
                      "startColumnIndex": col, "endColumnIndex": col + 1},
            "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP"}},
            "fields": "userEnteredFormat.wrapStrategy",
        }
    }


# ── Topics tab writer ──────────────────────────────────────────────────────────

def _batch_update(sheets_svc, spreadsheet_id: str, requests: list, chunk: int = 20) -> None:
    """Send batchUpdate requests in chunks with retry on 429 rate-limit errors."""
    import time
    from googleapiclient.errors import HttpError

    for i in range(0, len(requests), chunk):
        batch = requests[i:i + chunk]
        for attempt in range(5):
            try:
                sheets_svc.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={"requests": batch},
                ).execute()
                break
            except HttpError as e:
                if e.resp.status == 429:
                    wait = 15 * (attempt + 1)
                    print(f"  [sheets] Rate limited — waiting {wait}s...")
                    time.sleep(wait)
                else:
                    raise
        time.sleep(0.5)  # small pause between every chunk to stay under quota


def write_topics_tab(
    spreadsheet: gspread.Spreadsheet,
    gc: gspread.Client,
    rows: list[dict],
    variants: list[list[dict]],
    tab_name: str = "Topics",
) -> None:
    """
    Write topic candidates matching the reference design:
    - 8 columns: ⭐ | Idea | Proof | Search demand | Why it works | Keywords | Score | Status
    - Each topic has 10 variant rows beneath it, collapsed via row grouping (+/- toggle)
    - Top 3 rows: yellow tint + star
    - Score: red→green gradient
    - Status: dropdown
    - Proof: 2-line with clickable source link
    """
    ws = _ensure_tab(spreadsheet, tab_name)
    ws.clear()
    sheets_svc = _get_sheets_service(gc)
    sheet_id = ws.id
    n_topics = len(rows)

    _clean_sheet_state(sheets_svc, spreadsheet.id, sheet_id)

    # ── Build all rows (_STRIDE=12: 1 main + 1 sub-header + 10 variants) ────
    all_rows: list[list] = [TOPICS_HEADERS]
    for i, (row, topic_variants) in enumerate(zip(rows, variants)):
        proof_text = f"{row.get('proof_line1', '')}\n{row.get('proof_line2', '')}"
        # Main topic row
        all_rows.append([
            "⭐" if i < 3 else "",
            row.get("idea", ""),
            proof_text,
            row.get("search_demand", ""),
            row.get("why_it_works", ""),
            row.get("keywords", ""),
            row.get("score", 0),
            "Pending",
        ])
        # Variant sub-header (inside collapsed group)
        all_rows.append(_VARIANTS_SUBHEADER)
        # 10 variant rows
        for variant in topic_variants:
            all_rows.append([
                "",
                variant.get("variant_title", ""),
                variant.get("angle", ""),
                variant.get("what_modified", ""),
                variant.get("why_angle", ""),
                "", "", "",
            ])

    ws.update(range_name="A1", values=all_rows, value_input_option="USER_ENTERED")

    # ── Step 1: Add row groups (chunked — 10 topics per API call) ────────────
    # Group = rows [2+i*12, 13+i*12) = sub-header + 10 variants (11 rows)
    add_reqs = []
    for i in range(n_topics):
        start = 2 + i * _STRIDE
        end   = 13 + i * _STRIDE
        add_reqs.append({
            "addDimensionGroup": {
                "range": {"sheetId": sheet_id, "dimension": "ROWS",
                          "startIndex": start, "endIndex": end}
            }
        })
    _batch_update(sheets_svc, spreadsheet.id, add_reqs, chunk=10)

    # ── Step 2: Collapse all groups (chunked) ─────────────────────────────────
    collapse_reqs = []
    for i in range(n_topics):
        start = 2 + i * _STRIDE
        end   = 13 + i * _STRIDE
        collapse_reqs.append({
            "updateDimensionGroup": {
                "dimensionGroup": {
                    "range": {"sheetId": sheet_id, "dimension": "ROWS",
                              "startIndex": start, "endIndex": end},
                    "depth": 1,
                    "collapsed": True,
                },
                "fields": "collapsed",
            }
        })
    _batch_update(sheets_svc, spreadsheet.id, collapse_reqs, chunk=10)

    # ── Step 3: Formatting (chunked) ─────────────────────────────────────────
    max_row = 1 + n_topics * _STRIDE  # total rows including all variant blocks
    fmt = []

    # Top 3 main rows: yellow tint
    for i in range(min(3, n_topics)):
        fmt.append(_repeat_cell_bg(sheet_id, 1 + i * _STRIDE, 0, 8, _TOP3_BG))

    # Variant sub-header rows: gray
    for i in range(n_topics):
        fmt.append(_repeat_cell_bg(sheet_id, 2 + i * _STRIDE, 0, 8, _SUBHEADER_BG))

    # Angle badge (col C=2) on each variant row — colored by angle type
    for i, topic_variants in enumerate(variants):
        for j, variant in enumerate(topic_variants):
            var_row = 3 + i * _STRIDE + j
            angle = variant.get("angle", "")
            bg = _ANGLE_COLORS.get(angle, {"red": 0.5, "green": 0.5, "blue": 0.5})
            fmt.append({
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": var_row,
                              "endRowIndex": var_row + 1,
                              "startColumnIndex": 2, "endColumnIndex": 3},
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": bg,
                        "textFormat": {"foregroundColor": _WHITE, "bold": True},
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                    }},
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
                }
            })

    _batch_update(sheets_svc, spreadsheet.id, fmt, chunk=20)
    fmt = []

    # Proof column (col C=2): dark stats line + blue hyperlinked source line
    for i, row in enumerate(rows):
        line1 = row.get("proof_line1", "")
        line2 = row.get("proof_line2", "")
        url   = row.get("proof_url", "")
        link_start = _utf16_len(line1) + 1
        row_idx = 1 + i * _STRIDE

        runs = [{"startIndex": 0, "format": {"foregroundColorStyle": {"rgbColor": _DARK}}}]
        if url and line2:
            runs.append({
                "startIndex": link_start,
                "format": {
                    "foregroundColorStyle": {"rgbColor": _BLUE},
                    "underline": True,
                    "link": {"uri": url},
                },
            })
        fmt.append({
            "updateCells": {
                "rows": [{"values": [{"textFormatRuns": runs}]}],
                "range": {"sheetId": sheet_id, "startRowIndex": row_idx,
                          "endRowIndex": row_idx + 1,
                          "startColumnIndex": 2, "endColumnIndex": 3},
                "fields": "textFormatRuns",
            }
        })

    _batch_update(sheets_svc, spreadsheet.id, fmt, chunk=20)
    fmt = []

    # Score gradient: red→yellow→green on col G (index 6)
    fmt.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": max_row,
                            "startColumnIndex": 6, "endColumnIndex": 7}],
                "gradientRule": {
                    "minpoint": {"color": {"red": 0.96, "green": 0.26, "blue": 0.21}, "type": "MIN"},
                    "midpoint": {"color": {"red": 1.0, "green": 0.92, "blue": 0.23},
                                 "type": "PERCENTILE", "value": "50"},
                    "maxpoint": {"color": {"red": 0.20, "green": 0.66, "blue": 0.33}, "type": "MAX"},
                },
            },
            "index": 0,
        }
    })

    # Status dropdown on col H (index 7)
    fmt.append({
        "setDataValidation": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": max_row,
                      "startColumnIndex": 7, "endColumnIndex": 8},
            "rule": {
                "condition": {
                    "type": "ONE_OF_LIST",
                    "values": [
                        {"userEnteredValue": "Pending"},
                        {"userEnteredValue": "Selected"},
                        {"userEnteredValue": "Scripted"},
                        {"userEnteredValue": "Published"},
                    ],
                },
                "showCustomUi": True, "strict": True,
            }
        }
    })

    # Wrap all text columns — Idea, Proof, Search demand, Why it works, Keywords
    for col in [1, 2, 3, 4, 5]:
        fmt.append(_repeat_cell_wrap(sheet_id, 1, max_row, col))

    # Vertical alignment TOP for all data rows (text reads top-down, nothing hidden mid-cell)
    fmt.append({
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": max_row,
                      "startColumnIndex": 0, "endColumnIndex": 8},
            "cell": {"userEnteredFormat": {"verticalAlignment": "TOP"}},
            "fields": "userEnteredFormat.verticalAlignment",
        }
    })

    # Center ⭐ (col 0), Score (col 6), Status (col 7) horizontally
    for col in [0, 6, 7]:
        fmt.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": max_row,
                          "startColumnIndex": col, "endColumnIndex": col + 1},
                "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
                "fields": "userEnteredFormat.horizontalAlignment",
            }
        })

    # Column widths: ⭐=30, Idea=240, Proof=230, Demand=110, Why=320, Keywords=160, Score=65, Status=100
    for col_idx, px in enumerate([30, 240, 230, 110, 320, 160, 65, 100]):
        fmt.append({
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": col_idx, "endIndex": col_idx + 1},
                "properties": {"pixelSize": px},
                "fields": "pixelSize",
            }
        })

    # Freeze header row
    fmt.append({
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        }
    })

    _batch_update(sheets_svc, spreadsheet.id, fmt, chunk=20)

    # Auto-resize all rows to fit their content (run after data + formatting are written)
    sheets_svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet.id,
        body={"requests": [{
            "autoResizeDimensions": {
                "dimensions": {"sheetId": sheet_id, "dimension": "ROWS",
                               "startIndex": 0, "endIndex": max_row}
            }
        }]},
    ).execute()


def write_variants_tab(
    spreadsheet: gspread.Spreadsheet,
    gc: gspread.Client,
    rows: list[dict],
    variants: list[list[dict]],
) -> None:
    """
    Write all 10 angle variants per topic to a dedicated 'Variants' tab.
    Layout: header row, then for each topic — 1 bold topic header + 10 variant rows.
    """
    ws = _ensure_tab(spreadsheet, "Variants")
    ws.clear()
    sheets_svc = _get_sheets_service(gc)
    sheet_id = ws.id

    all_rows: list[list] = [VARIANTS_HEADERS]
    topic_header_indices: list[int] = []  # 1-indexed sheet rows that are topic headers

    for i, (row, topic_variants) in enumerate(zip(rows, variants)):
        topic_num = i + 1
        idea = row.get("idea", "")
        # Bold topic header row
        topic_header_indices.append(len(all_rows) + 1)
        all_rows.append([f"#{topic_num}", idea, "— 10 ANGLES BELOW —", "", "", ""])
        for variant in topic_variants:
            all_rows.append([
                topic_num,
                "",
                variant.get("angle", ""),
                variant.get("variant_title", ""),
                variant.get("what_modified", ""),
                variant.get("why_angle", ""),
            ])

    ws.update(range_name="A1", values=all_rows, value_input_option="USER_ENTERED")

    # Minimal formatting: gray topic header rows, freeze header, column widths
    fmt = []

    for sheet_row_idx in topic_header_indices:
        fmt.append(_repeat_cell_bg(sheet_id, sheet_row_idx, 0, 6, _SUBHEADER_BG))

    # Column widths: #=40, Topic=200, Angle=140, Variant Title=220, What Modified=200, Why=260
    for col_idx, px in enumerate([40, 200, 140, 220, 200, 260]):
        fmt.append({
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": col_idx, "endIndex": col_idx + 1},
                "properties": {"pixelSize": px},
                "fields": "pixelSize",
            }
        })

    # Freeze header
    fmt.append({
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        }
    })

    # Wrap Variant Title (col D=3) and Why (col F=5)
    max_row = len(all_rows)
    for col in [3, 5]:
        fmt.append(_repeat_cell_wrap(sheet_id, 1, max_row, col))

    if fmt:
        sheets_svc.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet.id, body={"requests": fmt}
        ).execute()


# ── Details tab writer ─────────────────────────────────────────────────────────

def write_details_tab(
    spreadsheet: gspread.Spreadsheet,
    gc: gspread.Client,
    detail_rows: list[dict],
) -> None:
    """Write hidden Details tab with all analyst metadata, one row per topic."""
    ws = _ensure_tab(spreadsheet, "Details")
    ws.clear()

    all_rows: list[list] = [DETAILS_HEADERS]
    for row in detail_rows:
        autocomplete = row.get("autocomplete_keywords", [])
        related = row.get("related_searches", [])
        tags = row.get("source_tags", [])
        all_rows.append([
            row.get("topic_num", ""),
            row.get("idea", ""),
            row.get("source_channel", ""),
            row.get("source_title", ""),
            row.get("source_url", ""),
            round(row.get("views_per_day", 0), 1),
            f"{row.get('engagement_rate', 0):.1%}",
            ", ".join(autocomplete) if isinstance(autocomplete, list) else str(autocomplete),
            ", ".join(related) if isinstance(related, list) else str(related),
            row.get("publish_date", ""),
            row.get("duration_seconds", ""),
            row.get("channel_tier", ""),
            "✓" if row.get("primary_competitor") else "",
            ", ".join(tags) if isinstance(tags, list) else str(tags),
            row.get("description_excerpt", ""),
            row.get("run_timestamp", ""),
        ])

    ws.update(range_name="A1", values=all_rows, value_input_option="USER_ENTERED")

    sheets_svc = _get_sheets_service(gc)
    sheets_svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet.id,
        body={"requests": [{"updateSheetProperties": {
            "properties": {"sheetId": ws.id, "hidden": True},
            "fields": "hidden",
        }}]},
    ).execute()


# ── Competitors tab writer ─────────────────────────────────────────────────────

def write_competitors_tab(
    spreadsheet: gspread.Spreadsheet,
    competitors: list[dict],
) -> None:
    """Write top competitors dashboard. Always overwrites."""
    ws = _ensure_tab(spreadsheet, "Top 10 Competitors")
    ws.clear()
    ws.append_row(COMPETITORS_HEADERS)
    rows = []
    for c in competitors:
        rows.append([
            c.get("rank", ""),
            c.get("name", ""),
            c.get("subs", 0),
            c.get("tier", ""),
            round(c.get("composite_score", 0), 4),
            round(c.get("uploads_per_month", 0), 1),
            c.get("median_views", 0),
            c.get("recent_median_views", 0),
            c.get("trajectory", "→"),
            f"{c.get('engagement_rate', 0):.1%}",
            c.get("breakout_1", ""),
            c.get("breakout_2", ""),
            c.get("breakout_3", ""),
            datetime.now().strftime("%Y-%m-%d"),
            "",
        ])
    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")


# ── Clusters tab writer ────────────────────────────────────────────────────────

def write_clusters_tab(
    spreadsheet: gspread.Spreadsheet,
    rows: list[dict],
    overwrite: bool = True,
) -> None:
    ws = _ensure_tab(spreadsheet, "Content Clusters")
    if overwrite:
        ws.clear()
    ws.append_row(CLUSTERS_HEADERS)
    data_rows = []
    for row in rows:
        views = row.get("source_views", 0)
        data_rows.append([
            row.get("cluster_id", ""),
            row.get("core_topic", ""),
            f"{views:,}" if views else "",
            row.get("source_channel", ""),
            row.get("video_type", ""),
            row.get("angle_lens", ""),
            row.get("suggested_title", ""),
            row.get("target_keyword", ""),
            row.get("why_this_works", ""),
            row.get("priority", "Medium"),
            "Idea",
        ])
    if data_rows:
        ws.append_rows(data_rows, value_input_option="USER_ENTERED")


# ── Row lookup helpers ─────────────────────────────────────────────────────────

def get_topic_row(spreadsheet: gspread.Spreadsheet, topic_number: int) -> dict:
    """Fetch topic metadata from Details tab by 1-based topic number."""
    ws = spreadsheet.worksheet("Details")
    headers = ws.row_values(1)
    data = ws.row_values(topic_number + 1)
    if not data:
        raise ValueError(f"Topic {topic_number} not found in the Details tab.")
    return dict(zip(headers, data))


def get_sheet_row(spreadsheet: gspread.Spreadsheet, row_number: int) -> dict:
    """Alias for get_topic_row."""
    return get_topic_row(spreadsheet, row_number)


def get_sheet_url(spreadsheet: gspread.Spreadsheet) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}/edit"


# ── Script doc writer ──────────────────────────────────────────────────────────

def _parse_markdown_runs(line: str) -> list[dict]:
    """Split a line into bold and normal runs for the Docs API."""
    import re
    runs = []
    for segment in re.split(r'(\*\*.*?\*\*)', line):
        if segment.startswith('**') and segment.endswith('**'):
            runs.append({"text": segment[2:-2], "bold": True})
        elif segment:
            runs.append({"text": segment, "bold": False})
    return runs


def create_script_doc(
    drive_service,
    docs_service,
    folder_id: str,
    title: str,
    content: str,
) -> str:
    """
    Create a Google Doc from markdown-style script content.
    Supports: # HEADING_1, ## HEADING_2, ### HEADING_3, **bold**, plain text, --- dividers.
    """
    doc = docs_service.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]

    # ── Pass 1: insert all text as plain, tracking per-line char ranges ────────
    lines = content.split("\n")
    plain_lines = []
    for line in lines:
        # Strip markdown heading markers and bold markers for plain insert
        stripped = line.lstrip("# ").replace("**", "")
        if line.strip() == "---":
            stripped = "─" * 40
        plain_lines.append(stripped)

    plain_text = "\n".join(plain_lines)
    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{"insertText": {"location": {"index": 1}, "text": plain_text}}]},
    ).execute()

    # ── Pass 2: apply paragraph styles + bold runs ────────────────────────────
    format_requests = []
    index = 1  # Docs API is 1-indexed; cursor starts at 1

    for raw_line, plain_line in zip(lines, plain_lines):
        line_len = len(plain_line) + 1  # +1 for the \n

        stripped = raw_line.strip()

        # Paragraph heading style
        if stripped.startswith("### "):
            style = "HEADING_3"
        elif stripped.startswith("## "):
            style = "HEADING_2"
        elif stripped.startswith("# "):
            style = "HEADING_1"
        else:
            style = None

        if style:
            format_requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": index, "endIndex": index + line_len},
                    "paragraphStyle": {"namedStyleType": style},
                    "fields": "namedStyleType",
                }
            })

        # Bold runs within the line
        if "**" in raw_line:
            run_cursor = index
            for run in _parse_markdown_runs(raw_line.lstrip("# ")):
                run_end = run_cursor + len(run["text"])
                if run["bold"]:
                    format_requests.append({
                        "updateTextStyle": {
                            "range": {"startIndex": run_cursor, "endIndex": run_end},
                            "textStyle": {"bold": True},
                            "fields": "bold",
                        }
                    })
                run_cursor = run_end

        index += line_len

    if format_requests:
        # Send in chunks to avoid payload limits
        for i in range(0, len(format_requests), 20):
            docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={"requests": format_requests[i:i + 20]},
            ).execute()

    # ── Move doc into the scripts folder ──────────────────────────────────────
    drive_service.files().update(
        fileId=doc_id, addParents=folder_id, removeParents="root", fields="id, parents"
    ).execute()

    return f"https://docs.google.com/document/d/{doc_id}/edit"
