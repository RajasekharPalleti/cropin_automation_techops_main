"""
Weekly Legacy Issues Report - SMFP (Services)

Queries Jira Cloud directly with the same JQL used by the
"Legacy issues - Service" dashboards (Overall + Last 4 weeks), builds an
Excel breakdown, and emails the summary to the configured recipients.

No Cropin login is required for this script (hide_auth = True in
app/script_configs.py) and no input file is required (requires_input = False).

Credentials (Jira API token + SMTP) are read from a local, git-ignored
config file: json_config/weekly_report_config.json — see
json_config/weekly_report_config.json.example for the expected format.
This keeps secrets out of the UI and out of source control, consistent
with how json_config/service_account.json / token.json are already
handled elsewhere in this app.

Inputs:
None required. This script ignores any uploaded input file.
"""

import base64
import json
import os
import smtplib
import datetime
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pandas as pd

CONFIG_PATH = os.path.join("json_config", "weekly_report_config.json")

# ==============================================================================
# JIRA JQL QUERIES
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. JQL_OVERALL (Current Live State — Older Than 30 Days)
# ------------------------------------------------------------------------------
# WHAT IT DOES:
#   Queries Jira for all currently open, legacy bugs older than 30 days.
# FILTERS:
#   - project = "SMFP" AND issuetype in (Bug, Bug-CS): Only SMFP project bugs.
#   - status NOT IN (Closed, "Ready For Testing"): Excludes resolved/tested/closed issues.
#   - priority in (High, Highest): Focuses only on critical and high-severity bugs.
#   - component = Services: Scoped to the Services component.
#   - created < -30d: Created strictly more than 30 days ago from today.
# WHERE USED:
#   - Current "Issues Older Than 30 Days" metric card (Total, Highest, High).
#   - Today's data point (rightmost) on the "Older Than 30 Days" trend chart.
#   - Target filter for the "View in Jira" button in the email.
JQL_OVERALL = (
    'project = "SMFP" and issuetype in (Bug, Bug-CS) '
    'and status NOT IN (Closed, "Ready For Testing") '
    'and priority in (High, Highest) AND component = Services '
    'and created < -30d order by priority DESC, created DESC'
)

# ------------------------------------------------------------------------------
# 2. JQL_LAST_4_WEEKS (Current Live State — Last 30 Days / Recent)
# ------------------------------------------------------------------------------
# WHAT IT DOES:
#   Queries Jira for all currently open bugs created within the last 30 days.
# FILTERS:
#   - project = "SMFP" AND issuetype in (Bug, Bug-CS): Only SMFP project bugs.
#   - status NOT IN (Closed, "Ready For Testing"): Excludes resolved/tested/closed issues.
#   - priority in (High, Highest): Focuses only on critical and high-severity bugs.
#   - component = Services: Scoped to the Services component.
#   - created >= -30d: Created within the last 30 days from today.
# WHERE USED:
#   - Current "Issues From Last 30 Days" metric card (Total, Highest, High).
#   - Today's data point (rightmost) on the "Last 30 Days" trend chart.
#   - Target filter for the "View in Jira" button in the email.
JQL_LAST_4_WEEKS = (
    'project = "SMFP" and issuetype in (Bug, Bug-CS) '
    'and status NOT IN (Closed, "Ready For Testing") '
    'and priority in (High, Highest) AND component = Services '
    'and created >= -30d order by priority DESC, created DESC'
)

# ------------------------------------------------------------------------------
# 3. JQL_HISTORY_OLDER (Historical Backfill — Older Than 30 Days As Of Friday {d})
# ------------------------------------------------------------------------------
# WHAT IT DOES:
#   Reconstructs the point-in-time open backlog as it existed on a past Friday {d}.
#   Because Jira does not store filter counts historically, this uses Jira Cloud's
#   changelog operators (WAS NOT IN ... ON / WAS IN ... ON) to inspect historical state.
# FILTERS:
#   - created <= "{d_minus_30}": Guarantees the issue existed and was > 30 days
#     old on that target Friday {d} (where d_minus_30 = d - 30 days).
#   - status WAS NOT IN (Closed, "Ready For Testing") ON "{d}": Checks changelog
#     at date {d} — issues closed AFTER date {d} are correctly included; issues
#     closed BEFORE date {d} are excluded.
#   - priority WAS IN (High, Highest) ON "{d}": Verifies that on that specific
#     date {d}, the priority was High or Highest.
# WHERE USED:
#   - Called for each of the past 26 Fridays (6 months) to plot the historical
#     points on the "Older Than 30 Days" trend chart.
JQL_HISTORY_OLDER = (
    'project = "SMFP" AND issuetype in (Bug, "Bug-CS") AND component = Services '
    'AND created <= "{d_minus_30}" '
    'AND status WAS NOT IN (Closed, "Ready For Testing") ON "{d}" '
    'AND priority WAS IN (High, Highest) ON "{d}"'
)

# ------------------------------------------------------------------------------
# 4. JQL_HISTORY_RECENT (Historical Backfill — Last 30 Days As Of Friday {d})
# ------------------------------------------------------------------------------
# WHAT IT DOES:
#   Reconstructs the recent open issues (created in the 30-day window ending on
#   Friday {d}) that were unresolved as of that Friday.
# FILTERS:
#   - created > "{d_minus_30}" AND created <= "{d}": Bounds creation to the
#     exact 30-day window prior to Friday {d}. Explicit created <= {d} avoids
#     Jira's historical search boundary bug.
#   - status WAS NOT IN (Closed, "Ready For Testing") ON "{d}": Confirms the
#     issue was open/unresolved on date {d}.
#   - priority WAS IN (High, Highest) ON "{d}": Confirms the priority was
#     High or Highest on date {d}.
# WHERE USED:
#   - Called for each of the past 26 Fridays (6 months) to plot the historical
#     points on the "Last 30 Days" trend chart.
JQL_HISTORY_RECENT = (
    'project = "SMFP" AND issuetype in (Bug, "Bug-CS") AND component = Services '
    'AND created > "{d_minus_30}" AND created <= "{d}" '
    'AND status WAS NOT IN (Closed, "Ready For Testing") ON "{d}" '
    'AND priority WAS IN (High, Highest) ON "{d}"'
)

FIELDS = ["key", "summary", "priority", "status", "created", "assignee"]


def _load_report_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(
            f"Missing {CONFIG_PATH}. Copy weekly_report_config.json.example to "
            "weekly_report_config.json in the same folder and fill in your "
            "Jira API token and SMTP credentials before running this script."
        )
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _jira_search(base_url, email, api_token, jql, log, max_results=100):
    auth = base64.b64encode(f"{email}:{api_token}".encode()).decode()
    all_issues = []
    next_page_token = None
    import ssl
    context = ssl._create_unverified_context()
    
    while True:
        payload = {
            "jql": jql,
            "maxResults": max_results,
            "fields": FIELDS,
        }
        if next_page_token:
            payload["nextPageToken"] = next_page_token
            
        body = json.dumps(payload).encode()
        req = Request(
            f"{base_url}/rest/api/3/search/jql",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(req, context=context) as resp:
                data = json.loads(resp.read().decode())
        except HTTPError as e:
            raise Exception(f"Jira API error {e.code}: {e.read().decode()}")

        issues = data.get("issues", [])
        all_issues.extend(issues)
        log(f"   ...fetched {len(all_issues)} / {data.get('total', '?')} issues")

        next_page_token = data.get("nextPageToken")
        if not next_page_token or not issues:
            break

    return all_issues


def _issue_row(issue):
    f = issue["fields"]
    return {
        "Key": issue["key"],
        "Summary": f.get("summary", ""),
        "Priority": (f.get("priority") or {}).get("name", "?"),
        "Status": (f.get("status") or {}).get("name", "?"),
        "Created": (f.get("created") or "")[:10],
        "Assignee": (f.get("assignee") or {}).get("displayName", "Unassigned"),
    }


def _format_issue_line(issue):
    r = _issue_row(issue)
    return f"{r['Key']} — {r['Summary']} | Priority: {r['Priority']} | Status: {r['Status']} | Created: {r['Created']} | Assignee: {r['Assignee']}"


def _get_past_fridays(num_weeks=20):
    """Return a list of the last `num_weeks` Fridays (as date objects), oldest first."""
    today = datetime.date.today()
    # 0=Monday ... 4=Friday
    days_since_friday = (today.weekday() - 4) % 7
    last_friday = today - datetime.timedelta(days=days_since_friday)
    fridays = [last_friday - datetime.timedelta(weeks=i) for i in range(num_weeks - 1, -1, -1)]
    return fridays


def _jira_count_by_priority(base_url, email, api_token, jql):
    """
    Fetch all issues for a JQL query (only priority field) and return
    (highest_count, high_count) by counting from the response.
    Single API call covers both priorities — halves the total requests.
    """
    import ssl, base64 as b64
    auth = b64.b64encode(f"{email}:{api_token}".encode()).decode()
    context = ssl._create_unverified_context()
    highest_count = 0
    high_count = 0
    next_page_token = None

    while True:
        payload = {"jql": jql, "maxResults": 100, "fields": ["priority"]}
        if next_page_token:
            payload["nextPageToken"] = next_page_token
        body = json.dumps(payload).encode()
        req = Request(
            f"{base_url}/rest/api/3/search/jql",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(req, context=context) as resp:
                data = json.loads(resp.read().decode())
        except Exception:
            break

        for issue in data.get("issues", []):
            p = (issue.get("fields") or {}).get("priority") or {}
            name = p.get("name", "")
            if name == "Highest":
                highest_count += 1
            elif name == "High":
                high_count += 1

        next_page_token = data.get("nextPageToken")
        if not next_page_token or not data.get("issues"):
            break

    return highest_count, high_count


def _fetch_trend_history(base_url, email, api_token, log, num_weeks=26):
    """
    Returns the trend history for the last `num_weeks` Fridays.
    Checks weekly_report_history.json first:
      - Uses existing historical data for dates already present (0 API calls).
      - Only queries Jira for missing Fridays (e.g. newly completed weeks).
      - Persists any newly fetched data into weekly_report_history.json.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    fridays = _get_past_fridays(num_weeks)
    HISTORY_PATH = os.path.join("json_config", "weekly_report_history.json")

    # 1. Load existing history from file if available
    existing = {}
    stored_rows = []
    if os.path.exists(HISTORY_PATH):
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                stored_rows = json.load(f)
                for row in stored_rows:
                    existing[row["date"]] = row
        except Exception as e:
            log(f"Warning: could not read {HISTORY_PATH}: {e}")

    # 2. Load all cached entries from history file
    cached_entries = []
    for row in stored_rows:
        d = row["date"]
        if isinstance(d, str):
            d = datetime.date.fromisoformat(d)
        cached_entries.append({
            "date": d,
            "older_highest": row["older_highest"],
            "older_high": row["older_high"],
            "recent_highest": row["recent_highest"],
            "recent_high": row["recent_high"],
        })

    # Identify which Fridays are missing from stored history
    missing_fridays = [friday for friday in fridays if friday.strftime("%Y-%m-%d") not in existing]

    # If all Fridays already exist in history file, return cached entries immediately (0 API calls)
    if not missing_fridays:
        log(f"Loaded all {len(cached_entries)} records directly from {HISTORY_PATH} (0 Jira API calls needed).")
        cached_entries.sort(key=lambda r: r["date"])
        return cached_entries

    log(f"Found {len(cached_entries)} cached Friday(s) in {HISTORY_PATH}. Fetching {len(missing_fridays)} missing Friday(s) from Jira ({len(missing_fridays) * 2} API calls, 6 workers)...")

    # 3. Fetch only missing Fridays from Jira in parallel
    completed = [0]

    def fetch_friday(friday):
        as_of_str = friday.strftime("%Y-%m-%d")
        cutoff_str = (friday - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
        older_highest, older_high = _jira_count_by_priority(
            base_url, email, api_token,
            JQL_HISTORY_OLDER.format(d_minus_30=cutoff_str, d=as_of_str)
        )
        recent_highest, recent_high = _jira_count_by_priority(
            base_url, email, api_token,
            JQL_HISTORY_RECENT.format(d_minus_30=cutoff_str, d=as_of_str)
        )
        return {
            "date": friday,
            "older_highest": older_highest,
            "older_high": older_high,
            "recent_highest": recent_highest,
            "recent_high": recent_high,
        }

    fetched_entries = []
    with ThreadPoolExecutor(max_workers=min(6, len(missing_fridays))) as executor:
        future_to_friday = {executor.submit(fetch_friday, friday): friday for friday in missing_fridays}
        for future in as_completed(future_to_friday):
            result = future.result()
            completed[0] += 1
            log(f"   [{completed[0]}/{len(missing_fridays)}] {result['date']} — Older: Highest={result['older_highest']}, High={result['older_high']} | Recent: Highest={result['recent_highest']}, High={result['recent_high']}")
            fetched_entries.append(result)

    # 4. Append newly fetched entries without modifying/disturbing any existing entries
    try:
        for entry in fetched_entries:
            date_str = entry["date"].strftime("%Y-%m-%d")
            # Strictly append only missing dates; existing entries are never touched
            if date_str not in existing:
                existing[date_str] = {
                    "date": date_str,
                    "older_highest": entry["older_highest"],
                    "older_high": entry["older_high"],
                    "recent_highest": entry["recent_highest"],
                    "recent_high": entry["recent_high"],
                }
        sorted_history = sorted(existing.values(), key=lambda r: r["date"])
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted_history, f, indent=2)
        log(f"Appended {len(fetched_entries)} new entry/entries to {HISTORY_PATH} ({len(sorted_history)} total stored).")
    except Exception as e:
        log(f"Warning: could not update {HISTORY_PATH}: {e}")

    # Combine cached and newly fetched, sort oldest to newest
    all_history = cached_entries + fetched_entries
    all_history.sort(key=lambda r: r["date"])
    return all_history


def _generate_trend_chart(history, highest_key, high_key, title):
    """Generate a trend line chart from history data with all dates shown and consistent colors."""
    import matplotlib
    matplotlib.use('agg')
    import matplotlib.pyplot as plt
    import io
    import datetime

    # Prepare labels for all dates
    today_obj = datetime.date.today()
    dates_str = []
    for h in history:
        d = h["date"]
        if isinstance(d, str):
            d = datetime.date.fromisoformat(d)
        label = d.strftime("%d-%b")
        if d == today_obj:
            label += " (Today)"
        dates_str.append(label)

    highest_vals = [h[highest_key] for h in history]
    high_vals = [h[high_key] for h in history]

    fig, ax = plt.subplots(figsize=(15, 4.2), dpi=150)
    fig.patch.set_facecolor('#ffffff')
    ax.set_facecolor('#fafbfc')

    x = list(range(len(history)))

    c_highest = "#DE350B"  # Jira Crimson Red
    c_high = "#FF8B00"     # Jira Amber Orange

    # Draw lines
    ax.plot(x, highest_vals, color=c_highest, linewidth=2.4, marker='o', markersize=6, label='Highest Priority', zorder=4)
    ax.plot(x, high_vals, color=c_high, linewidth=2.4, marker='s', markersize=6, label='High Priority', zorder=3)

    # Label data points with smart collision avoidance
    for i in x:
        hv = highest_vals[i]
        hi = high_vals[i]

        if abs(hv - hi) <= 1:
            if hi >= hv:
                ax.annotate(str(hi), (i, hi), textcoords="offset points", xytext=(0, 7),
                            ha="center", fontsize=8.5, color=c_high, fontweight="bold")
                ax.annotate(str(hv), (i, hv), textcoords="offset points", xytext=(0, -14),
                            ha="center", fontsize=8.5, color=c_highest, fontweight="bold")
            else:
                ax.annotate(str(hv), (i, hv), textcoords="offset points", xytext=(0, 7),
                            ha="center", fontsize=8.5, color=c_highest, fontweight="bold")
                ax.annotate(str(hi), (i, hi), textcoords="offset points", xytext=(0, -14),
                            ha="center", fontsize=8.5, color=c_high, fontweight="bold")
        else:
            ax.annotate(str(hv), (i, hv), textcoords="offset points", xytext=(0, 7),
                        ha="center", fontsize=8.5, color=c_highest, fontweight="bold")
            ax.annotate(str(hi), (i, hi), textcoords="offset points", xytext=(0, 7),
                        ha="center", fontsize=8.5, color=c_high, fontweight="bold")

    max_y = max(max(highest_vals), max(high_vals)) if highest_vals and high_vals else 10
    min_y = min(min(highest_vals), min(high_vals)) if highest_vals and high_vals else 0
    ax.set_ylim(max(-1.5, min_y - 2.5), max_y + 3.5)
    ax.set_xlim(-0.6, len(x) - 0.4)

    # All dates shown on X axis
    ax.set_xticks(x)
    ax.set_xticklabels(dates_str, rotation=55, ha="right", fontsize=8, color="#42526E")

    ax.set_title(title, fontsize=12, fontweight="bold", color="#172B4D", pad=28)
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, 1.13), ncol=2, frameon=True, facecolor="#ffffff", edgecolor="#DFE1E6", fontsize=9.5)

    for spine in ax.spines.values():
        spine.set_color("#DFE1E6")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.set_visible(False)
    ax.grid(axis="y", linestyle="--", alpha=0.5, color="#EBECF0")

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    plt.close()
    buf.seek(0)
    return buf.read()


def _build_email_body(base_url, overall_issues, recent_issues, trend_history):
    overall_highest = sum(1 for i in overall_issues if i["fields"].get("priority", {}).get("name") == "Highest")
    overall_high = sum(1 for i in overall_issues if i["fields"].get("priority", {}).get("name") == "High")
    overall_total = overall_highest + overall_high

    recent_highest = sum(1 for i in recent_issues if i["fields"].get("priority", {}).get("name") == "Highest")
    recent_high = sum(1 for i in recent_issues if i["fields"].get("priority", {}).get("name") == "High")
    recent_total = recent_highest + recent_high

    overall_jql_encoded = urllib.parse.quote(JQL_OVERALL)
    recent_jql_encoded = urllib.parse.quote(JQL_LAST_4_WEEKS)

    overall_link = f"{base_url}/jira/software/c/projects/SMFP/issues/?filter=allissues&jql={overall_jql_encoded}"
    recent_link = f"{base_url}/jira/software/c/projects/SMFP/issues/?filter=allissues&jql={recent_jql_encoded}"

    overall_img_data = _generate_trend_chart(trend_history, "older_highest", "older_high", "Older Than 30 Days — Trend (Last 6 Months)")
    recent_img_data = _generate_trend_chart(trend_history, "recent_highest", "recent_high", "Last 30 Days — Trend (Last 6 Months)")

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #172B4D; background-color: #f4f5f7; margin: 0; padding: 20px 10px; }}
            .container {{ width: 100%; max-width: 980px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #DFE1E6; overflow: hidden; box-shadow: 0 1px 3px rgba(9, 30, 66, 0.08); }}
            .header {{ background: linear-gradient(135deg, #0052CC 0%, #0747A6 100%); color: white; padding: 24px 30px; text-align: center; }}
            .header-title {{ font-size: 20px; font-weight: 700; letter-spacing: 0.3px; margin: 0; }}
            .header-subtitle {{ font-size: 13px; opacity: 0.85; margin-top: 5px; }}
            .content {{ padding: 28px 30px; }}
            .section {{ margin-bottom: 28px; border: 1px solid #DFE1E6; border-radius: 8px; padding: 22px; background: #FAFBFC; }}
            .section-title {{ font-size: 16px; font-weight: 700; color: #0052CC; margin: 0; }}
            .btn {{ background-color: #0052CC; color: #ffffff !important; padding: 7px 16px; text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: 600; display: inline-block; transition: background 0.2s; }}
            .btn:hover {{ background-color: #0747A6; }}
            .chart-container {{ text-align: center; background: #ffffff; border-radius: 6px; border: 1px solid #DFE1E6; padding: 12px 6px; margin-top: 15px; box-shadow: 0 1px 2px rgba(9, 30, 66, 0.04); }}
            .chart-img {{ width: 100%; max-width: 100%; height: auto; display: block; }}
            .footer {{ border-top: 1px solid #DFE1E6; padding-top: 20px; margin-top: 10px; color: #5E6C84; font-size: 13px; text-align: left; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="header-title">Weekly Legacy Issues Report</div>
                <div class="header-subtitle">SMFP / Services • Quality & Stability Tracking</div>
            </div>
            <div class="content">
                <p style="margin-top: 0; color: #172B4D; font-size: 14px;">Hi Team,</p>
                <p style="color: #42526E; font-size: 14px; margin-bottom: 22px;">Please find below the weekly summary of open Highest and High priority issues in Jira for the Services component.</p>
                
                <!-- Overall Section -->
                <div class="section">
                    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 16px;">
                        <tr>
                            <td align="left" style="font-size: 16px; font-weight: 700; color: #0052CC;">
                                Issues Older Than 30 Days
                            </td>
                            <td align="right">
                                <a href="{overall_link}" class="btn">View in Jira &rarr;</a>
                            </td>
                        </tr>
                    </table>
                    
                    <!-- 3-Card Indicator Layout -->
                    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 18px;">
                        <tr>
                            <!-- Total Card -->
                            <td width="31%" style="background-color: #F4F5F7; border: 1px solid #DFE1E6; border-left: 5px solid #0052CC; border-radius: 6px; padding: 14px 18px;">
                                <div style="font-size: 11px; font-weight: 700; color: #5E6C84; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">Total Open Issues</div>
                                <div style="font-size: 28px; font-weight: 800; color: #172B4D; line-height: 1.1;">{overall_total}</div>
                                <div style="font-size: 11px; color: #6B778C; margin-top: 4px;">Older than 30 days</div>
                            </td>
                            <td width="3.5%"></td>
                            <!-- Highest Card -->
                            <td width="31%" style="background-color: #FFF0ED; border: 1px solid #FFBDAD; border-left: 5px solid #DE350B; border-radius: 6px; padding: 14px 18px;">
                                <div style="font-size: 11px; font-weight: 700; color: #BF2600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">&#9679; Highest Priority</div>
                                <div style="font-size: 28px; font-weight: 800; color: #DE350B; line-height: 1.1;">{overall_highest}</div>
                                <div style="font-size: 11px; color: #BF2600; margin-top: 4px;">Immediate attention required</div>
                            </td>
                            <td width="3.5%"></td>
                            <!-- High Card -->
                            <td width="31%" style="background-color: #FFF9E6; border: 1px solid #FFE380; border-left: 5px solid #FF8B00; border-radius: 6px; padding: 14px 18px;">
                                <div style="font-size: 11px; font-weight: 700; color: #B76E00; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">&#9679; High Priority</div>
                                <div style="font-size: 28px; font-weight: 800; color: #D97008; line-height: 1.1;">{overall_high}</div>
                                <div style="font-size: 11px; color: #B76E00; margin-top: 4px;">Target for sprint resolution</div>
                            </td>
                        </tr>
                    </table>
                    
                    <div class="chart-container">
                        <img src="cid:overall_chart" alt="Overall Issues Trend" class="chart-img">
                    </div>
                </div>
                
                <!-- Recent Section -->
                <div class="section">
                    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 16px;">
                        <tr>
                            <td align="left" style="font-size: 16px; font-weight: 700; color: #0052CC;">
                                Issues From Last 30 Days
                            </td>
                            <td align="right">
                                <a href="{recent_link}" class="btn">View in Jira &rarr;</a>
                            </td>
                        </tr>
                    </table>
                    
                    <!-- 3-Card Indicator Layout -->
                    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 18px;">
                        <tr>
                            <!-- Total Card -->
                            <td width="31%" style="background-color: #F4F5F7; border: 1px solid #DFE1E6; border-left: 5px solid #0052CC; border-radius: 6px; padding: 14px 18px;">
                                <div style="font-size: 11px; font-weight: 700; color: #5E6C84; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">Total Recent Issues</div>
                                <div style="font-size: 28px; font-weight: 800; color: #172B4D; line-height: 1.1;">{recent_total}</div>
                                <div style="font-size: 11px; color: #6B778C; margin-top: 4px;">Opened in last 4 weeks</div>
                            </td>
                            <td width="3.5%"></td>
                            <!-- Highest Card -->
                            <td width="31%" style="background-color: #FFF0ED; border: 1px solid #FFBDAD; border-left: 5px solid #DE350B; border-radius: 6px; padding: 14px 18px;">
                                <div style="font-size: 11px; font-weight: 700; color: #BF2600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">&#9679; Highest Priority</div>
                                <div style="font-size: 28px; font-weight: 800; color: #DE350B; line-height: 1.1;">{recent_highest}</div>
                                <div style="font-size: 11px; color: #BF2600; margin-top: 4px;">Immediate attention required</div>
                            </td>
                            <td width="3.5%"></td>
                            <!-- High Card -->
                            <td width="31%" style="background-color: #FFF9E6; border: 1px solid #FFE380; border-left: 5px solid #FF8B00; border-radius: 6px; padding: 14px 18px;">
                                <div style="font-size: 11px; font-weight: 700; color: #B76E00; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">&#9679; High Priority</div>
                                <div style="font-size: 28px; font-weight: 800; color: #D97008; line-height: 1.1;">{recent_high}</div>
                                <div style="font-size: 11px; color: #B76E00; margin-top: 4px;">Target for sprint resolution</div>
                            </td>
                        </tr>
                    </table>
                    
                    <div class="chart-container">
                        <img src="cid:recent_chart" alt="Recent Issues Trend" class="chart-img">
                    </div>
                </div>

                <div class="footer">
                    Regards,<br>
                    <strong>Rajasekhar Palleti</strong><br>
                    QA Engineer | Cropin
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return html, overall_img_data, recent_img_data


def _send_email(cfg, subject, body, overall_img_data, recent_img_data):
    from email.mime.image import MIMEImage
    
    smtp_host = cfg["smtp_host"]
    smtp_port = int(cfg["smtp_port"])
    smtp_user = cfg["smtp_user"]
    smtp_password = cfg["smtp_password"]
    mail_from = cfg.get("mail_from", smtp_user)
    mail_to = [addr.strip() for addr in cfg.get("mail_to", "").split(",") if addr.strip()]
    mail_cc = [addr.strip() for addr in cfg.get("mail_cc", "").split(",") if addr.strip()]

    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = ", ".join(mail_to)
    if mail_cc:
        msg["Cc"] = ", ".join(mail_cc)

    msg_alt = MIMEMultipart("alternative")
    msg.attach(msg_alt)
    msg_alt.attach(MIMEText(body, "html"))

    if overall_img_data:
        img1 = MIMEImage(overall_img_data)
        img1.add_header('Content-ID', '<overall_chart>')
        msg.attach(img1)
        
    if recent_img_data:
        img2 = MIMEImage(recent_img_data)
        img2.add_header('Content-ID', '<recent_chart>')
        msg.attach(img2)

    import ssl
    context = ssl._create_unverified_context()
    
    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30, context=context) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(mail_from, mail_to + mail_cc, msg.as_string())
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls(context=context)
            server.login(smtp_user, smtp_password)
            server.sendmail(mail_from, mail_to + mail_cc, msg.as_string())


def run(input_excel, output_excel, config, log_callback=None, action="send"):
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)

    log("Loading Jira/SMTP config from json_config/weekly_report_config.json...")
    cfg = _load_report_config()

    base_url = cfg["jira_base_url"].rstrip("/")
    jira_email = cfg["jira_email"]
    jira_api_token = cfg["jira_api_token"]

    CACHE_PATH = os.path.join("json_config", "weekly_report_cache.json")
    import time

    use_cache = False
    if action == "send" and os.path.exists(CACHE_PATH):
        if time.time() - os.path.getmtime(CACHE_PATH) < 1800:  # 30 mins
            try:
                with open(CACHE_PATH, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                    overall_issues = cache_data.get("overall_issues")
                    recent_issues = cache_data.get("recent_issues")
                    trend_history_raw = cache_data.get("trend_history")
                    if overall_issues is not None and recent_issues is not None and trend_history_raw is not None:
                        # Restore date objects from strings
                        trend_history = [
                            {**r, "date": datetime.date.fromisoformat(r["date"]) if isinstance(r["date"], str) else r["date"]}
                            for r in trend_history_raw
                        ]
                        use_cache = True
                        log("Using cached Jira data from the recent Fetch...")
                        log(f"Found {len(overall_issues)} overall legacy issue(s).")
                        log(f"Found {len(recent_issues)} issue(s) from the last 4 weeks.")
                        log(f"Loaded {len(trend_history)} trend history data points from cache.")
            except Exception:
                pass

    if not use_cache:
        log("Querying Jira: OVERALL legacy issues (open > 30 days)...")
        overall_issues = _jira_search(base_url, jira_email, jira_api_token, JQL_OVERALL, log)
        log(f"Found {len(overall_issues)} overall legacy issue(s).")

        log("Querying Jira: issues opened in LAST 4 WEEKS...")
        recent_issues = _jira_search(base_url, jira_email, jira_api_token, JQL_LAST_4_WEEKS, log)
        log(f"Found {len(recent_issues)} issue(s) from the last 4 weeks.")

        # --- Build today's data point from fetched issues (no extra API calls) ---
        today_date = datetime.date.today()
        today_older_highest  = sum(1 for i in overall_issues if (i["fields"].get("priority") or {}).get("name") == "Highest")
        today_older_high     = sum(1 for i in overall_issues if (i["fields"].get("priority") or {}).get("name") == "High")
        today_recent_highest = sum(1 for i in recent_issues  if (i["fields"].get("priority") or {}).get("name") == "Highest")
        today_recent_high    = sum(1 for i in recent_issues  if (i["fields"].get("priority") or {}).get("name") == "High")
        today_entry = {
            "date": today_date,
            "older_highest": today_older_highest,
            "older_high": today_older_high,
            "recent_highest": today_recent_highest,
            "recent_high": today_recent_high,
        }
        log(f"Today ({today_date}) — Older: Highest={today_older_highest}, High={today_older_high} | Recent: Highest={today_recent_highest}, High={today_recent_high}")

        # --- Load or fetch past 26 Fridays (6 months) history ---
        log("Loading historical trend data for past 26 Fridays (6 months)...")
        trend_history = _fetch_trend_history(base_url, jira_email, jira_api_token, log, num_weeks=26)

        # Check the last date in historical trend data:
        # If triggered on Friday, prune any intermediate non-Friday ("middle date") records so the chart shows pure weekly intervals
        if today_date.weekday() == 4:
            trend_history = [
                r for r in trend_history
                if (datetime.date.fromisoformat(r["date"]) if isinstance(r["date"], str) else r["date"]).weekday() == 4
            ]

        # Current date details are always sent along with history on the chart:
        if trend_history:
            last_entry_date = trend_history[-1]["date"]
            if isinstance(last_entry_date, str):
                last_entry_date = datetime.date.fromisoformat(last_entry_date)
            days_diff = (today_date - last_entry_date).days
            if days_diff > 0:
                trend_history.append(today_entry)
                log(f"Last historical date was {last_entry_date} ({days_diff} days ago) — added triggered date ({today_date}) to trend chart.")
            else:
                trend_history[-1] = today_entry
                log(f"Updated today's ({today_date}) data on trend chart with live counts.")
        else:
            trend_history.append(today_entry)

        # Save to weekly_report_history.json when it's more than 3 days (>= 3 days) since the last saved record:
        HISTORY_PATH = os.path.join("json_config", "weekly_report_history.json")
        try:
            history_file_data = []
            if os.path.exists(HISTORY_PATH):
                with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                    history_file_data = json.load(f)

            today_str = today_date.strftime("%Y-%m-%d")
            today_save_entry = {
                "date": today_str,
                "older_highest": today_older_highest,
                "older_high": today_older_high,
                "recent_highest": today_recent_highest,
                "recent_high": today_recent_high,
            }

            # When triggered on Friday (weekday 4), remove any intermediate non-Friday ("middle date") records
            if today_date.weekday() == 4 and history_file_data:
                non_fridays = [
                    r for r in history_file_data
                    if (datetime.date.fromisoformat(r["date"]) if isinstance(r["date"], str) else r["date"]).weekday() != 4
                ]
                if non_fridays:
                    history_file_data = [
                        r for r in history_file_data
                        if (datetime.date.fromisoformat(r["date"]) if isinstance(r["date"], str) else r["date"]).weekday() == 4
                    ]
                    log(f"Today is Friday ({today_str}): cleaned up {len(non_fridays)} middle date record(s) ({', '.join(r['date'] for r in non_fridays)}) from history file.")

            if history_file_data:
                last_saved_date_str = history_file_data[-1]["date"]
                last_saved_date = datetime.date.fromisoformat(last_saved_date_str) if isinstance(last_saved_date_str, str) else last_saved_date_str
                save_diff = (today_date - last_saved_date).days

                if save_diff >= 3:
                    history_file_data.append(today_save_entry)
                    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
                        json.dump(history_file_data, f, indent=2)
                    log(f"Last saved history was {last_saved_date} ({save_diff} days ago, >= 3 days) — saved {today_str} record to {HISTORY_PATH}.")
                elif save_diff == 0:
                    history_file_data[-1] = today_save_entry
                    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
                        json.dump(history_file_data, f, indent=2)
                    log(f"Updated today's ({today_str}) record in {HISTORY_PATH} with live counts.")
                else:
                    log(f"Last saved history was {last_saved_date} ({save_diff} days ago, < 3 days) — included in current report, but not saved to {HISTORY_PATH}.")
            else:
                history_file_data.append(today_save_entry)
                with open(HISTORY_PATH, "w", encoding="utf-8") as f:
                    json.dump(history_file_data, f, indent=2)
                log(f"Saved initial record {today_str} to {HISTORY_PATH}.")
        except Exception as e:
            log(f"Warning: could not update {HISTORY_PATH}: {e}")

        # --- Save everything to cache ---
        try:
            cache_payload = {
                "overall_issues": overall_issues,
                "recent_issues": recent_issues,
                "trend_history": [
                    {**r, "date": r["date"].strftime("%Y-%m-%d") if hasattr(r["date"], "strftime") else r["date"]}
                    for r in trend_history
                ],
            }
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache_payload, f)
            log(f"Trend history and issue data saved to cache ({len(trend_history)} data points).")
        except Exception as e:
            log(f"Warning: could not save cache: {e}")

    if action == "fetch":
        log("Data fetch complete (including trend history). Please review before sending the email.")
        return

    body, overall_img, recent_img = _build_email_body(base_url, overall_issues, recent_issues, trend_history)
    today = datetime.date.today().strftime("%d %b %Y")
    subject = f"Weekly Legacy Issues Report — SMFP / Services — {today}"

    mail_to_str = cfg.get('mail_to', '')
    mail_cc_str = cfg.get('mail_cc', '')
    if mail_cc_str:
        log(f"Sending email to: {mail_to_str} (CC: {mail_cc_str})")
    else:
        log(f"Sending email to: {mail_to_str}")

    _send_email(cfg, subject, body, overall_img, recent_img)
    log("Email sent successfully.")
