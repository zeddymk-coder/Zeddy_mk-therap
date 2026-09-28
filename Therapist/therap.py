import os
import sqlite3
import html
import urllib.parse
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename


APP_DIR = Path(__file__).resolve().parent
load_dotenv(APP_DIR / ".env")

st.set_page_config(
    page_title="Soft Touch | Wellness Studio",
    page_icon="♡",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = Path(os.getenv("SOFT_TOUCH_DB_PATH", str(APP_DIR / "soft_touch_database.db")))
UPLOAD_DIR = APP_DIR / "static" / "model_images"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ADMIN_USERNAME = os.getenv("SOFT_TOUCH_ADMIN_USERNAME", "")
ADMIN_PASSWORD_HASH = os.getenv("SOFT_TOUCH_ADMIN_PASSWORD_HASH", "")
DISPATCH_PHONE = os.getenv("SOFT_TOUCH_DISPATCH_PHONE", "255695989995")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_SIZE = 16 * 1024 * 1024
VIDEO_EXTENSIONS = {".mp4", ".webm"}
MAX_VIDEO_SIZE = 50 * 1024 * 1024
GMT_PLUS_3 = timezone(timedelta(hours=3), name="GMT+3")
DURATION_OPTIONS = [30, 45, 60, 90, 120, 150, 180]
TANZANIA_CITIES = [
    "Arusha",
    "Bukoba",
    "Dar es Salaam",
    "Dodoma",
    "Iringa",
    "Kigoma",
    "Mbeya",
    "Morogoro",
    "Moshi",
    "Mtwara",
    "Mwanza",
    "Musoma",
    "Shinyanga",
    "Songea",
    "Tabora",
    "Tanga",
    "Zanzibar City",
    "Other",
]


@contextmanager
def database():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize_database():
    with database() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS service (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(150) NOT NULL,
                price FLOAT NOT NULL,
                location_scope VARCHAR(50) NOT NULL,
                description TEXT,
                duration_minutes INTEGER NOT NULL DEFAULT 30
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS model_profile (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL,
                tier_assignment VARCHAR(20) DEFAULT 'Standard',
                age INTEGER NOT NULL,
                skin_color VARCHAR(50) NOT NULL,
                languages_spoken VARCHAR(200) NOT NULL,
                about_text TEXT,
                photo_filename VARCHAR(250) NOT NULL DEFAULT '',
                video_filename VARCHAR(250) NOT NULL DEFAULT '',
                ethnicity VARCHAR(100) NOT NULL DEFAULT '',
                nationality VARCHAR(100) NOT NULL DEFAULT '',
                city VARCHAR(100) NOT NULL DEFAULT ''
            )"""
        )
        service_columns = {
            column["name"] for column in connection.execute("PRAGMA table_info(service)")
        }
        if "photo_filename" not in service_columns:
            connection.execute(
                "ALTER TABLE service ADD COLUMN photo_filename VARCHAR(250) NOT NULL DEFAULT ''"
            )
        if "video_filename" not in service_columns:
            connection.execute(
                "ALTER TABLE service ADD COLUMN video_filename VARCHAR(250) NOT NULL DEFAULT ''"
            )
        if "duration_minutes" not in service_columns:
            connection.execute(
                "ALTER TABLE service ADD COLUMN duration_minutes INTEGER NOT NULL DEFAULT 30"
            )
        profile_columns = {
            column["name"] for column in connection.execute("PRAGMA table_info(model_profile)")
        }
        if "video_filename" not in profile_columns:
            connection.execute(
                "ALTER TABLE model_profile ADD COLUMN video_filename VARCHAR(250) NOT NULL DEFAULT ''"
            )
        for column_name in ("ethnicity", "nationality", "city"):
            if column_name not in profile_columns:
                connection.execute(
                    f"ALTER TABLE model_profile ADD COLUMN {column_name} VARCHAR(100) NOT NULL DEFAULT ''"
                )


def get_services():
    with database() as connection:
        return connection.execute(
            "SELECT * FROM service ORDER BY name COLLATE NOCASE"
        ).fetchall()


def get_profiles(tier=None):
    with database() as connection:
        if tier:
            return connection.execute(
                "SELECT * FROM model_profile WHERE tier_assignment = ? ORDER BY name COLLATE NOCASE",
                (tier,),
            ).fetchall()
        return connection.execute(
            "SELECT * FROM model_profile ORDER BY name COLLATE NOCASE"
        ).fetchall()


def format_duration(minutes):
    hours, remaining_minutes = divmod(int(minutes), 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour" if hours == 1 else f"{hours} hours")
    if remaining_minutes:
        parts.append(f"{remaining_minutes} minutes")
    return " ".join(parts)


def get_time_greeting(current_time=None):
    local_time = current_time or datetime.now(GMT_PLUS_3)
    local_time = local_time.astimezone(GMT_PLUS_3)
    if 5 <= local_time.hour < 12:
        message = "Good morning 😊"
    elif 12 <= local_time.hour < 17:
        message = "Good afternoon 😊"
    elif 17 <= local_time.hour < 21:
        message = "Good evening 😊"
    else:
        message = "Good night 😊"
    display_time = local_time.strftime("%I:%M %p").lstrip("0")
    return message, display_time


def render_time_greeting():
    message, display_time = get_time_greeting()
    typing_duration = 3.25
    character_duration = 0.14
    delay_step = (typing_duration - character_duration) / max(len(message) - 1, 1)
    animated_message = "".join(
        f'<span class="greeting-character" style="animation-delay:{index * delay_step:.3f}s">'
        f'{"&nbsp;" if character == " " else html.escape(character)}</span>'
        for index, character in enumerate(message)
    )
    st.markdown(
        '<div class="time-greeting"><div class="time-greeting-content">'
        f'<div class="time-greeting-message">{animated_message}</div>'
        '<div class="time-greeting-subtitle">Take a breath and let a little warmth find its way to you.</div>'
        f'</div><div class="time-greeting-clock">{display_time} · GMT+3</div></div>',
        unsafe_allow_html=True,
    )


def render_admin_table(rows):
    if not rows:
        return
    headers = list(rows[0])
    header_html = "".join(f"<th>{html.escape(str(header))}</th>" for header in headers)
    body_html = []
    for row in rows:
        cells = []
        for header in headers:
            value = row[header]
            numeric_class = "numeric" if isinstance(value, (int, float)) else ""
            if isinstance(value, float):
                value = f"{value:,.0f}"
            cells.append(
                f'<td class="{numeric_class}">{html.escape(str(value if value is not None else ""))}</td>'
            )
        body_html.append("<tr>" + "".join(cells) + "</tr>")
    st.markdown(
        '<div class="admin-table-wrap"><table class="admin-table">'
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{''.join(body_html)}</tbody></table></div>",
        unsafe_allow_html=True,
    )


def apply_theme():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@500;600;700&display=swap');
        :root {
            --ink: #30282a;
            --wine: #873d4d;
            --wine-dark: #682d3b;
            --petal: #f4e5e5;
            --sage: #607365;
        }
        .stApp {
            color: var(--ink);
            background: radial-gradient(ellipse at 88% 4%, rgba(210, 151, 154, .17), transparent 34rem),
                linear-gradient(145deg, #fffaf8 0%, #fbf4f1 54%, #f6eceb 100%);
            font-family: 'DM Sans', sans-serif;
        }
        h1, h2, h3, [data-testid="stMarkdownContainer"] h1,
        [data-testid="stMarkdownContainer"] h2,
        [data-testid="stMarkdownContainer"] h3 {
            color: #56313b;
            font-family: 'Playfair Display', Georgia, serif;
            letter-spacing: 0;
        }
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #f3e6e5 0%, #f8efed 100%);
            border-right: 1px solid rgba(104, 45, 59, .12);
        }
        section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: #65575a; }
        div[data-testid="stButton"] > button,
        div[data-testid="stFormSubmitButton"] > button,
        div[data-testid="stLinkButton"] > a {
            min-height: 2.7rem;
            border: 1px solid var(--wine);
            border-radius: 7px;
            background: var(--wine);
            color: #fffaf8;
            font-weight: 600;
            transition: background .16s ease, border-color .16s ease, transform .16s ease;
        }
        div[data-testid="stButton"] > button:hover,
        div[data-testid="stFormSubmitButton"] > button:hover,
        div[data-testid="stLinkButton"] > a:hover {
            border-color: var(--wine-dark);
            background: var(--wine-dark);
            color: #fff;
            transform: translateY(-1px);
        }
        div[data-testid="stButton"] > button:focus,
        div[data-testid="stFormSubmitButton"] > button:focus,
        div[data-testid="stLinkButton"] > a:focus { box-shadow: 0 0 0 .2rem rgba(135, 61, 77, .2); }
        div[data-testid="stButton"] > button:disabled { border-color: #c9b9b8; background: #d9cdcb; color: #fff; }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
            width: 100%;
            justify-content: flex-start;
            min-height: 2.8rem;
            border-radius: 8px;
            padding-left: 1rem;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"] {
            border-color: rgba(135, 61, 77, .16);
            background: rgba(255, 250, 248, .74);
            color: #713947;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"]:hover {
            border-color: #bd7880;
            background: #f1dfe1;
            color: #682d3b;
        }
        [data-testid="stSegmentedControl"] {
            padding: .18rem;
            border: 1px solid rgba(135, 61, 77, .18);
            border-radius: 8px;
            background: #f3e6e5;
        }
        [data-testid="stSegmentedControl"] button[aria-pressed="true"] {
            border-radius: 6px;
            background: var(--wine);
            color: #fffaf8;
        }
        [data-testid="stTextInput"] input, [data-testid="stNumberInput"] input,
        [data-testid="stTextArea"] textarea, [data-testid="stSelectbox"] div[data-baseweb="select"] > div {
            border-color: #d9c4c3;
            border-radius: 6px;
        }
        [data-testid="stNumberInput"] button { display: none !important; }
        [data-testid="stNumberInput"] input[type="number"] {
            appearance: textfield;
            -moz-appearance: textfield;
        }
        [data-testid="stNumberInput"] input[type="number"]::-webkit-inner-spin-button,
        [data-testid="stNumberInput"] input[type="number"]::-webkit-outer-spin-button {
            margin: 0;
            -webkit-appearance: none;
        }
        .admin-table-wrap { overflow-x: auto; border: 1px solid #e4d1d2; border-radius: 8px; background: #fffdfc; }
        table.admin-table { width: 100%; border-collapse: collapse; color: #403538; font-size: .92rem; }
        .admin-table th { padding: .8rem .95rem; border-bottom: 1px solid #dfc9cb; background: #f2e4e4; color: #713947; font-weight: 700; text-align: left; }
        .admin-table td { padding: .75rem .95rem; border-bottom: 1px solid #eee3e2; }
        .admin-table tbody tr:nth-child(even) { background: #fff9f8; }
        .admin-table tbody tr:hover { background: #f8eeee; }
        .admin-table tbody tr:last-child td { border-bottom: 0; }
        .admin-table td.numeric { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
        [data-testid="stMetric"] { padding: .8rem 1rem; border: 1px solid rgba(104, 45, 59, .12); border-radius: 7px; background: rgba(255, 250, 248, .78); }
        .brand-kicker, .section-label { color: var(--sage); font-size: .76rem; font-weight: 700; text-transform: uppercase; }
        .brand-title { margin: .1rem 0 .2rem; color: #56313b; font-family: 'Playfair Display', Georgia, serif; font-size: 2.5rem; line-height: 1.12; }
        .brand-copy { max-width: 42rem; color: #65575a; font-size: 1.03rem; line-height: 1.65; }
        .vip-copy { margin: 1rem 0; color: #56313b; font-size: 1.15rem; font-weight: 600; line-height: 1.7; }
        .vip-copy-label { display: block; margin-bottom: .35rem; color: var(--sage); font-size: .76rem; font-weight: 700; text-transform: uppercase; }
        .tier-label { color: var(--wine); font-size: .78rem; font-weight: 700; text-transform: uppercase; }
        .profile-details { margin: .65rem 0 1rem; }
        .profile-detail-row { display: grid; grid-template-columns: minmax(90px, .8fr) minmax(0, 2fr); gap: .75rem; padding: .38rem 0; border-bottom: 1px solid rgba(104, 45, 59, .1); line-height: 1.45; }
        .profile-detail-key { color: #713947; font-weight: 700; }
        .profile-detail-value { color: #4f4547; overflow-wrap: anywhere; }
        .time-greeting { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; margin: 0 0 1.4rem; padding: .9rem 0 1rem; border-bottom: 1px solid rgba(104, 45, 59, .16); }
        .time-greeting-content { min-width: 0; }
        .time-greeting-message { color: #713947; font-family: 'Playfair Display', Georgia, serif; font-size: 2.2rem; font-weight: 600; line-height: 1.2; }
        .greeting-character { display: inline-block; opacity: 0; animation: greeting-type .14s ease-out forwards; }
        .time-greeting-subtitle { margin-top: .45rem; color: #65575a; font-size: 1.02rem; line-height: 1.5; }
        .time-greeting-clock { flex: 0 0 auto; padding-top: .55rem; color: #75686a; font-size: .82rem; font-weight: 600; white-space: nowrap; }
        @keyframes greeting-type { to { opacity: 1; transform: translateY(0); } from { opacity: 0; transform: translateY(.12em); } }
        @media (max-width: 640px) { .time-greeting { flex-direction: column; gap: .25rem; } .time-greeting-message { font-size: 1.8rem; } .time-greeting-clock { padding-top: 0; } }
        @media (prefers-reduced-motion: reduce) { .greeting-character { opacity: 1; animation: none; } }
        </style>
        """,
        unsafe_allow_html=True,
    )
    if st.session_state.get("dark_mode", False):
        st.markdown(
            """
            <style>
            :root { color-scheme: dark; }
            .stApp { color: #f3e8e7; background: radial-gradient(ellipse at 86% 4%, rgba(135, 61, 77, .2), transparent 34rem), linear-gradient(145deg, #211b1d 0%, #292123 55%, #302326 100%); }
            .stApp h1, .stApp h2, .stApp h3, .stApp [data-testid="stMarkdownContainer"] h1, .stApp [data-testid="stMarkdownContainer"] h2, .stApp [data-testid="stMarkdownContainer"] h3 { color: #f1dfe1; }
            .stApp [data-testid="stMarkdownContainer"] p, .stApp [data-testid="stCaptionContainer"], .stApp label, .stApp [data-testid="stWidgetLabel"] { color: #e1d2d3; }
            section[data-testid="stSidebar"] { background: linear-gradient(180deg, #241c1f 0%, #302326 100%); border-color: #49353a; }
            section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p, section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: #d9c6c8; }
            div[data-testid="stButton"] > button, div[data-testid="stFormSubmitButton"] > button, div[data-testid="stLinkButton"] > a { border: 1px solid #d2949e !important; background: #873d4d !important; color: #fffaf8 !important; box-shadow: 0 1px 3px rgba(0, 0, 0, .28); }
            div[data-testid="stButton"] > button:hover, div[data-testid="stFormSubmitButton"] > button:hover, div[data-testid="stLinkButton"] > a:hover { border-color: #edb5bd !important; background: #a64f60 !important; color: #fff !important; }
            div[data-testid="stButton"] > button:focus-visible, div[data-testid="stFormSubmitButton"] > button:focus-visible, div[data-testid="stLinkButton"] > a:focus-visible { outline: 3px solid #f3c3ca !important; outline-offset: 2px; box-shadow: 0 0 0 4px rgba(135, 61, 77, .45) !important; }
            div[data-testid="stButton"] > button:disabled { border-color: #71565b !important; background: #49383c !important; color: #bbaeb0 !important; }
            section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"] { border-color: #9a6a73 !important; background: #39272d !important; color: #ffeef0 !important; }
            section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"]:hover { border-color: #edb5bd !important; background: #52343d !important; color: #fff !important; }
            section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] { border-color: #edb5bd !important; background: #873d4d !important; color: #fffaf8 !important; }
            section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"]:hover { background: #a64f60 !important; }
            [data-testid="stVerticalBlockBorderWrapper"], [data-testid="stExpander"] { border-color: #59464b; background-color: rgba(48, 36, 40, .86); }
            [data-testid="stTextInput"] input, [data-testid="stNumberInput"] input, [data-testid="stTextArea"] textarea, [data-testid="stSelectbox"] div[data-baseweb="select"] > div { border-color: #604a50; background-color: #342a2d; color: #f3e8e7; }
            [data-testid="stFileUploader"] section { border-color: #604a50; background-color: #302629; }
            [data-testid="stSegmentedControl"] { border-color: #604a50; background: #382a2f; }
            [data-testid="stSegmentedControl"] button { color: #f0dfe1; }
            [data-testid="stAlert"] { border-color: #70515a; background-color: #392b30; color: #f3e8e7; }
            .admin-table-wrap { border-color: #59464b; background: #2a2225; }
            table.admin-table { color: #f0e5e4; }
            .admin-table th { border-color: #59464b; background: #48333a; color: #f5dfe3; }
            .admin-table td { border-color: #49383d; }
            .admin-table tbody tr:nth-child(even) { background: #302629; }
            .admin-table tbody tr:hover { background: #443238; }
            .profile-detail-row { border-color: #59464b; }
            .profile-detail-key, .profile-detail-value { color: #f0dfe1; }
            .time-greeting-message, .vip-copy { color: #f2dce0; }
            .time-greeting-subtitle, .time-greeting-clock { color: #d9c6c8; }
            [data-testid="stMetric"] { border-color: #59464b; background: #302629; color: #f3e8e7; }
            </style>
            """,
            unsafe_allow_html=True,
        )


def render_profile(profile):
    photo_name = Path(profile["photo_filename"] or "").name
    photo_path = UPLOAD_DIR / photo_name
    if photo_name and photo_path.is_file() and photo_path.suffix.lower() in IMAGE_EXTENSIONS:
        st.image(str(photo_path), use_container_width=True)
    video_name = Path(profile["video_filename"] or "").name
    video_path = UPLOAD_DIR / video_name
    if video_name and video_path.is_file() and video_path.suffix.lower() in VIDEO_EXTENSIONS:
        st.video(str(video_path))
    st.caption("Model")
    st.subheader(profile["name"])
    details = [
        ("Age", profile["age"]),
        ("Ethnicity", profile["ethnicity"]),
        ("Nationality", profile["nationality"]),
        ("City", profile["city"]),
        ("Languages", profile["languages_spoken"]),
    ]
    detail_rows = "".join(
        f'<div class="profile-detail-row"><span class="profile-detail-key">{html.escape(label)}</span>'
        f'<span class="profile-detail-value">{html.escape(str(value))}</span></div>'
        for label, value in details
        if value
    )
    st.markdown(f'<div class="profile-details">{detail_rows}</div>', unsafe_allow_html=True)
    if profile["about_text"]:
        st.write(profile["about_text"])
    message = (
        "Hello SOFT TOUCH Dispatch Office, I am requesting a service slot with "
        f'the following therapist:\n\n{profile["name"]} '
        f'({profile["tier_assignment"]} Tier), age {profile["age"]}, '
        f'{profile["ethnicity"]}, {profile["nationality"]}, based in {profile["city"]}; '
        f'languages: {profile["languages_spoken"]}.\n\n'
        "Please share available scheduling windows."
    )
    whatsapp_url = f"https://wa.me/{DISPATCH_PHONE}?{urllib.parse.urlencode({'text': message})}"
    st.link_button("Request a session", whatsapp_url, use_container_width=True)


def render_mobile_fare_notice(service_id):
    language = st.segmented_control(
        "Fare notice language",
        ["English", "Kiswahili"],
        default="English",
        key=f"fare_language_{service_id}",
        label_visibility="collapsed",
    )
    if language == "Kiswahili":
        st.info("Kwa huduma ya kwenda kwa mteja, nauli ya usafiri hulipwa na mteja.")
    else:
        st.info("For mobile service, transportation fare is paid by the client.")


def render_service_location(service):
    location_scope = service["location_scope"]
    if location_scope == "Both":
        st.caption("Available: Mobile & In-Office")
        selected_location = st.segmented_control(
            "Choose service location",
            ["Mobile", "In-Office"],
            default="In-Office",
            key=f"service_location_{service['id']}",
        )
        if selected_location == "Mobile":
            render_mobile_fare_notice(service["id"])
    elif location_scope == "Mobile":
        st.caption("Available: Mobile")
        render_mobile_fare_notice(service["id"])
    else:
        st.caption("Available: In-Office")


def render_discover():
    st.markdown('<div class="brand-kicker">SOFT TOUCH · WELLNESS STUDIO</div>', unsafe_allow_html=True)
    st.markdown('<div class="brand-title">A softer hour, just for you.</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="brand-copy">Thoughtful treatments, warm conversation, and space to settle into yourself.</div>',
        unsafe_allow_html=True,
    )
    st.write("")
    st.markdown("### Treatments")
    services = get_services()
    if services:
        columns = st.columns(min(3, len(services)))
        for index, service in enumerate(services):
            with columns[index % len(columns)]:
                with st.container(border=True):
                    image_name = Path(service["photo_filename"] or "").name
                    image_path = UPLOAD_DIR / image_name
                    if image_name and image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTENSIONS:
                        st.image(str(image_path), use_container_width=True)
                    video_name = Path(service["video_filename"] or "").name
                    video_path = UPLOAD_DIR / video_name
                    if video_name and video_path.is_file() and video_path.suffix.lower() in VIDEO_EXTENSIONS:
                        st.video(str(video_path))
                    st.markdown(f"#### {service['name']}")
                    st.markdown(f"**{service['price']:,.0f} TZS**")
                    st.caption(f"Duration: {format_duration(service['duration_minutes'])}")
                    render_service_location(service)
                    if service["description"]:
                        st.write(service["description"])
    else:
        st.caption("Treatment details will appear here soon.")

    st.divider()
    st.markdown("### Meet the therapists")
    profiles = get_profiles("Standard")
    if profiles:
        columns = st.columns(min(3, len(profiles)))
        for index, profile in enumerate(profiles):
            with columns[index % len(columns)]:
                with st.container(border=True):
                    render_profile(profile)


def render_vip():
    st.markdown('<div class="section-label">A little more extraordinary</div>', unsafe_allow_html=True)
    st.markdown("## Your private moment begins here")
    st.markdown(
        '<div class="vip-copy"><span class="vip-copy-label">English</span>'
        "Step into our five-star model collection: A considered selection of beautiful, "
        "accomplished models, each introduced through her real portrait. Take your "
        "time exploring the photographs and profiles, then choose the person whose "
        "presence feels right for your moment.</div>"
        '<div class="vip-copy"><span class="vip-copy-label">Kiswahili</span>'
        "Karibu katika mkusanyiko wetu wa WAREMBO nyota tano: Uteuzi maalum wa wanamitindo "
        "warembo na wenye mvuto, kila mmoja akionyeshwa kupitia picha yake halisi. "
        "Tazama picha na wasifu kwa utulivu, kisha mchague anayekuvutia na anayekufaa "
        "kwa wakati wako wa faragha na mapumziko.</div>",
        unsafe_allow_html=True,
    )
    st.caption("Every profile in this collection includes a portrait photo. Your request opens a WhatsApp draft for you to review and send.")
    st.info("This is a private-collection preview. No payment is processed in this app.")
    if not st.session_state.get("soft_touch_vip_unlocked"):
        if st.button("Preview the private collection", icon=":material/favorite:"):
            st.session_state.soft_touch_vip_unlocked = True
    else:
        profiles = [
            profile for profile in get_profiles("VIP")
            if profile["photo_filename"]
            and (UPLOAD_DIR / Path(profile["photo_filename"]).name).is_file()
            and Path(profile["photo_filename"]).suffix.lower() in IMAGE_EXTENSIONS
        ]
        if profiles:
            columns = st.columns(min(3, len(profiles)))
            for index, profile in enumerate(profiles):
                with columns[index % len(columns)]:
                    with st.container(border=True):
                        render_profile(profile)
        else:
            st.caption("The private collection is being prepared. New profiles will appear here with their portraits.")


def render_about():
    st.markdown('<div class="section-label">Our approach</div>', unsafe_allow_html=True)
    st.markdown("## About Soft Touch")
    st.write(
        "Soft Touch is a wellness studio for guests looking for a thoughtful, "
        "personal massage experience. Browse available treatments and therapist "
        "profiles, then contact the studio to discuss your preferences and confirm availability."
    )
    st.write(
        "We aim to make the first step simple: clear treatment information, "
        "a direct way to reach the studio, and a welcoming conversation before booking."
    )


def render_faq():
    st.markdown('<div class="section-label">A few helpful details</div>', unsafe_allow_html=True)
    st.markdown("## Frequently asked questions")
    questions = [
        (
            "How do I book a session?",
            "Choose a therapist and select Request a session, or message the studio from Contact. "
            "Your booking is not confirmed until the studio replies with availability.",
        ),
        (
            "Where can I find treatment prices?",
            "Open Discover and browse Treatments. Prices and service locations are shown when the studio has added them.",
        ),
        (
            "Does the WhatsApp button send a message automatically?",
            "No. It opens a pre-filled WhatsApp chat so you can review and send the message yourself.",
        ),
        (
            "Is VIP access a payment checkout?",
            "No. The private collection is currently a demo preview; this app does not process payments.",
        ),
        (
            "How can I ask about a change or cancellation?",
            "Contact the studio directly on WhatsApp so the team can confirm the arrangements for your booking.",
        ),
    ]
    for question, answer in questions:
        with st.expander(question):
            st.write(answer)


def render_contact():
    st.markdown('<div class="section-label">We are here to help</div>', unsafe_allow_html=True)
    st.markdown("## Contact the studio")
    st.write("Message us to ask about treatments, therapist availability, or an existing booking.")
    st.link_button(
        "Message us on WhatsApp",
        f"https://wa.me/{DISPATCH_PHONE}?{urllib.parse.urlencode({'text': 'Hello Soft Touch, I would like to ask about booking a session.'})}",
        icon=":material/chat:",
    )
    st.caption("WhatsApp opens with a draft message. Review it and press Send in WhatsApp.")


def save_uploaded_media(upload, media_kind, allowed_extensions, max_size):
    if upload is None:
        return ""
    extension = Path(upload.name).suffix.lower()
    if extension not in allowed_extensions:
        raise ValueError(f"Choose a supported {media_kind} file.")
    file_data = upload.getvalue()
    if len(file_data) > max_size:
        raise ValueError(f"{media_kind.title()} files must be {max_size // (1024 * 1024)} MB or smaller.")
    cleaned_name = secure_filename(Path(upload.name).stem) or media_kind
    filename = f"{uuid.uuid4().hex}_{cleaned_name}{extension}"
    (UPLOAD_DIR / filename).write_bytes(file_data)
    return filename


def save_uploaded_image(photo, image_kind):
    return save_uploaded_media(photo, image_kind, IMAGE_EXTENSIONS, MAX_IMAGE_SIZE)


def save_uploaded_video(video, video_kind):
    return save_uploaded_media(video, video_kind, VIDEO_EXTENSIONS, MAX_VIDEO_SIZE)


def add_service(name, price, location, description, duration_minutes, photo, video):
    filename = save_uploaded_image(photo, "treatment")
    video_filename = save_uploaded_video(video, "treatment video")
    with database() as connection:
        connection.execute(
            "INSERT INTO service (name, price, location_scope, description, duration_minutes, photo_filename, video_filename) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name.strip(), float(price), location, description.strip(), int(duration_minutes), filename, video_filename),
        )


def update_service(service_id, name, price, location, description, duration_minutes, photo, video):
    filename = save_uploaded_image(photo, "treatment")
    video_filename = save_uploaded_video(video, "treatment video")
    with database() as connection:
        if filename or video_filename:
            connection.execute(
                """UPDATE service SET name = ?, price = ?, location_scope = ?,
                description = ?, duration_minutes = ?,
                photo_filename = COALESCE(NULLIF(?, ''), photo_filename),
                video_filename = COALESCE(NULLIF(?, ''), video_filename) WHERE id = ?""",
                (name.strip(), float(price), location, description.strip(), int(duration_minutes), filename, video_filename, service_id),
            )
        else:
            connection.execute(
                """UPDATE service SET name = ?, price = ?, location_scope = ?,
                description = ?, duration_minutes = ? WHERE id = ?""",
                (name.strip(), float(price), location, description.strip(), int(duration_minutes), service_id),
            )


def add_profile(name, tier, age, ethnicity, nationality, city, languages, about, photo, video):
    if tier == "VIP" and photo is None:
        raise ValueError("A portrait photo is required for the private collection.")
    filename = save_uploaded_image(photo, "portrait")
    video_filename = save_uploaded_video(video, "profile video")
    with database() as connection:
        connection.execute(
            """INSERT INTO model_profile
            (name, tier_assignment, age, skin_color, languages_spoken, about_text,
            photo_filename, video_filename, ethnicity, nationality, city)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name.strip(), tier, int(age), "", languages.strip(), about.strip(),
                filename, video_filename, ethnicity.strip(), nationality.strip(), city.strip(),
            ),
        )


def update_profile(profile_id, name, tier, age, ethnicity, nationality, city, languages, about, photo, video):
    if tier == "VIP" and photo is None:
        with database() as connection:
            existing = connection.execute(
                "SELECT photo_filename FROM model_profile WHERE id = ?", (profile_id,)
            ).fetchone()
        existing_photo = Path(existing["photo_filename"] or "").name if existing else ""
        photo_path = UPLOAD_DIR / existing_photo
        if (
            not existing_photo
            or not photo_path.is_file()
            or photo_path.suffix.lower() not in IMAGE_EXTENSIONS
        ):
            raise ValueError("A portrait photo is required for the private collection.")
    filename = save_uploaded_image(photo, "portrait")
    video_filename = save_uploaded_video(video, "profile video")
    with database() as connection:
        if filename or video_filename:
            connection.execute(
                """UPDATE model_profile SET name = ?, tier_assignment = ?, age = ?,
                ethnicity = ?, nationality = ?, city = ?, languages_spoken = ?, about_text = ?,
                photo_filename = COALESCE(NULLIF(?, ''), photo_filename),
                video_filename = COALESCE(NULLIF(?, ''), video_filename)
                WHERE id = ?""",
                (
                    name.strip(), tier, int(age), ethnicity.strip(), nationality.strip(), city.strip(),
                    languages.strip(), about.strip(), filename, video_filename, profile_id,
                ),
            )
        else:
            connection.execute(
                """UPDATE model_profile SET name = ?, tier_assignment = ?, age = ?,
                ethnicity = ?, nationality = ?, city = ?, languages_spoken = ?, about_text = ?
                WHERE id = ?""",
                (
                    name.strip(), tier, int(age), ethnicity.strip(), nationality.strip(), city.strip(),
                    languages.strip(), about.strip(), profile_id,
                ),
            )


def queue_save_notification(message):
    st.session_state["save_notification"] = message
    st.rerun()


def show_save_notification():
    message = st.session_state.pop("save_notification", None)
    if message:
        st.toast(message, icon=":material/check_circle:")


def render_admin():
    st.markdown("## Studio administration")
    if not st.session_state.get("soft_touch_admin"):
        if not ADMIN_USERNAME or not ADMIN_PASSWORD_HASH:
            st.warning("Admin access is not configured. Set SOFT_TOUCH_ADMIN_USERNAME and SOFT_TOUCH_ADMIN_PASSWORD_HASH in Therapist/.env.")
            return
        with st.form("admin_login"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", use_container_width=True)
        if submitted:
            if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
                st.session_state.soft_touch_admin = True
                st.rerun()
            st.error("The username or password is incorrect.")
        return

    if st.button("Sign out", icon=":material/logout:"):
        st.session_state.pop("soft_touch_admin", None)
        st.rerun()

    service_tab, profile_tab = st.tabs(["Treatments", "Therapist profiles"])
    with service_tab:
        with st.form("add_service", clear_on_submit=True):
            st.markdown("### Add a treatment")
            service_name = st.text_input("Treatment name")
            service_price = st.number_input("Price (TZS)", min_value=0.0, step=5000.0)
            service_duration = st.selectbox(
                "Treatment duration",
                DURATION_OPTIONS,
                index=0,
                format_func=format_duration,
                key="new_service_duration",
            )
            service_location = st.selectbox(
                "Available at",
                ["Both", "Mobile", "In-Office"],
                format_func=lambda value: "Mobile & In-Office" if value == "Both" else value,
            )
            service_description = st.text_area("Description")
            service_photo = st.file_uploader("Treatment photo (JPG, PNG, or WebP; max 16 MB)", type=["jpg", "jpeg", "png", "webp"], key="new_service_photo")
            service_video = st.file_uploader("Short treatment video (MP4 or WebM; max 50 MB)", type=["mp4", "webm"], key="new_service_video")
            save_service = st.form_submit_button("Add treatment", use_container_width=True)
        if save_service:
            if not service_name.strip() or service_price <= 0:
                st.error("Enter a treatment name and a price greater than zero.")
            else:
                try:
                    add_service(service_name, service_price, service_location, service_description, service_duration, service_photo, service_video)
                except ValueError as error:
                    st.error(str(error))
                else:
                    queue_save_notification("Treatment added successfully.")
        services = get_services()
        if services:
            with st.expander("Edit a treatment", expanded=False):
                service_by_id = {row["id"]: row for row in services}
                selected_service_id = st.selectbox(
                    "Choose a treatment",
                    list(service_by_id),
                    format_func=lambda service_id: service_by_id[service_id]["name"],
                    key="edit_service_choice",
                )
                selected_service = service_by_id[selected_service_id]
                current_service_image = Path(selected_service["photo_filename"] or "").name
                current_service_path = UPLOAD_DIR / current_service_image
                if current_service_image and current_service_path.is_file():
                    st.image(str(current_service_path), width=220)
                current_service_video = Path(selected_service["video_filename"] or "").name
                current_service_video_path = UPLOAD_DIR / current_service_video
                if current_service_video and current_service_video_path.is_file():
                    st.video(str(current_service_video_path))
                with st.form("edit_service", clear_on_submit=True):
                    edited_service_name = st.text_input("Treatment name", value=selected_service["name"], key="edit_service_name")
                    edited_service_price = st.number_input("Price (TZS)", min_value=0.0, value=float(selected_service["price"]), step=5000.0, key="edit_service_price")
                    saved_duration = selected_service["duration_minutes"] or 30
                    edited_service_duration = st.selectbox(
                        "Treatment duration",
                        DURATION_OPTIONS,
                        index=DURATION_OPTIONS.index(saved_duration) if saved_duration in DURATION_OPTIONS else 0,
                        format_func=format_duration,
                        key="edit_service_duration",
                    )
                    locations = ["Both", "Mobile", "In-Office"]
                    current_location_index = locations.index(selected_service["location_scope"]) if selected_service["location_scope"] in locations else 0
                    edited_service_location = st.selectbox(
                        "Available at",
                        locations,
                        index=current_location_index,
                        format_func=lambda value: "Mobile & In-Office" if value == "Both" else value,
                        key="edit_service_location",
                    )
                    edited_service_description = st.text_area("Description", value=selected_service["description"] or "", key="edit_service_description")
                    edited_service_photo = st.file_uploader("Replace treatment photo (leave empty to keep current)", type=["jpg", "jpeg", "png", "webp"], key="edit_service_photo")
                    edited_service_video = st.file_uploader("Replace treatment video (leave empty to keep current)", type=["mp4", "webm"], key="edit_service_video")
                    update_service_button = st.form_submit_button("Save treatment changes", use_container_width=True)
                if update_service_button:
                    if not edited_service_name.strip() or edited_service_price <= 0:
                        st.error("Enter a treatment name and a price greater than zero.")
                    else:
                        try:
                            update_service(selected_service_id, edited_service_name, edited_service_price, edited_service_location, edited_service_description, edited_service_duration, edited_service_photo, edited_service_video)
                        except ValueError as error:
                            st.error(str(error))
                        else:
                            queue_save_notification("Treatment updated successfully.")
            render_admin_table(
                [
                    {
                        "Treatment": row["name"],
                        "Duration": format_duration(row["duration_minutes"]),
                        "Price (TZS)": row["price"],
                        "Available at": row["location_scope"],
                    }
                    for row in services
                ]
            )

    with profile_tab:
        with st.form("add_profile", clear_on_submit=True):
            st.markdown("### Add a therapist profile")
            name = st.text_input("Name")
            tier = st.selectbox("Collection", ["Standard", "VIP"])
            age = st.number_input("Age", min_value=18, max_value=100, value=18)
            ethnicity = st.text_input("Ethnicity")
            nationality = st.text_input("Nationality", value="Tanzania")
            city_choice = st.selectbox("City in Tanzania", TANZANIA_CITIES, key="new_profile_city")
            city = st.text_input("Enter city", key="new_profile_custom_city") if city_choice == "Other" else city_choice
            languages = st.text_input("Languages spoken")
            about = st.text_area("About", height=180, placeholder="Write a short introduction for the therapist profile...")
            photo = st.file_uploader("Portrait (JPG, PNG, or WebP; max 16 MB)", type=["jpg", "jpeg", "png", "webp"])
            video = st.file_uploader("Short profile video (MP4 or WebM; max 50 MB)", type=["mp4", "webm"], key="new_profile_video")
            save_profile = st.form_submit_button("Add profile", use_container_width=True)
        if save_profile:
            if not name.strip() or not ethnicity.strip() or not nationality.strip() or not city.strip() or not languages.strip():
                st.error("Name, ethnicity, nationality, city, and languages are required.")
            else:
                try:
                    add_profile(name, tier, age, ethnicity, nationality, city, languages, about, photo, video)
                except ValueError as error:
                    st.error(str(error))
                else:
                    queue_save_notification("Therapist profile added successfully.")
        profiles = get_profiles()
        if profiles:
            with st.expander("Edit a therapist profile", expanded=False):
                profile_by_id = {row["id"]: row for row in profiles}
                selected_profile_id = st.selectbox(
                    "Choose a profile",
                    list(profile_by_id),
                    format_func=lambda profile_id: f"{profile_by_id[profile_id]['name']} · {profile_by_id[profile_id]['tier_assignment']}",
                    key="edit_profile_choice",
                )
                selected_profile = profile_by_id[selected_profile_id]
                current_photo_name = Path(selected_profile["photo_filename"] or "").name
                current_photo_path = UPLOAD_DIR / current_photo_name
                if current_photo_name and current_photo_path.is_file():
                    st.image(str(current_photo_path), width=220)
                current_profile_video = Path(selected_profile["video_filename"] or "").name
                current_profile_video_path = UPLOAD_DIR / current_profile_video
                if current_profile_video and current_profile_video_path.is_file():
                    st.video(str(current_profile_video_path))
                with st.form("edit_profile", clear_on_submit=True):
                    edited_name = st.text_input("Name", value=selected_profile["name"], key="edit_profile_name")
                    tiers = ["Standard", "VIP"]
                    current_tier_index = tiers.index(selected_profile["tier_assignment"]) if selected_profile["tier_assignment"] in tiers else 0
                    edited_tier = st.selectbox("Collection", tiers, index=current_tier_index, key="edit_profile_tier")
                    edited_age = st.number_input("Age", min_value=18, max_value=100, value=max(18, selected_profile["age"]), key="edit_profile_age")
                    edited_ethnicity = st.text_input("Ethnicity", value=selected_profile["ethnicity"], key="edit_profile_ethnicity")
                    edited_nationality = st.text_input("Nationality", value=selected_profile["nationality"] or "Tanzania", key="edit_profile_nationality")
                    saved_city = selected_profile["city"] or ""
                    edited_city_choice = st.selectbox(
                        "City in Tanzania",
                        TANZANIA_CITIES,
                        index=TANZANIA_CITIES.index(saved_city) if saved_city in TANZANIA_CITIES else len(TANZANIA_CITIES) - 1,
                        key="edit_profile_city",
                    )
                    edited_city = (
                        st.text_input(
                            "Enter city",
                            value=saved_city if saved_city not in TANZANIA_CITIES else "",
                            key="edit_profile_custom_city",
                        )
                        if edited_city_choice == "Other"
                        else edited_city_choice
                    )
                    edited_languages = st.text_input("Languages spoken", value=selected_profile["languages_spoken"], key="edit_profile_languages")
                    edited_about = st.text_area(
                        "About",
                        value=selected_profile["about_text"] or "",
                        height=180,
                        placeholder="Write a short introduction for the therapist profile...",
                        key="edit_profile_about",
                    )
                    replacement_photo = st.file_uploader("Replace portrait (leave empty to keep current)", type=["jpg", "jpeg", "png", "webp"], key="edit_profile_photo")
                    replacement_video = st.file_uploader("Replace profile video (leave empty to keep current)", type=["mp4", "webm"], key="edit_profile_video")
                    update_profile_button = st.form_submit_button("Save profile changes", use_container_width=True)
                if update_profile_button:
                    if not edited_name.strip() or not edited_ethnicity.strip() or not edited_nationality.strip() or not edited_city.strip() or not edited_languages.strip():
                        st.error("Name, ethnicity, nationality, city, and languages are required.")
                    else:
                        try:
                            update_profile(
                                selected_profile_id,
                                edited_name,
                                edited_tier,
                                edited_age,
                                edited_ethnicity,
                                edited_nationality,
                                edited_city,
                                edited_languages,
                                edited_about,
                                replacement_photo,
                                replacement_video,
                            )
                        except ValueError as error:
                            st.error(str(error))
                        else:
                            queue_save_notification("Therapist profile updated successfully.")
            render_admin_table(
                [
                    {"Name": row["name"], "Collection": row["tier_assignment"], "Age": row["age"], "Languages": row["languages_spoken"]}
                    for row in profiles
                ]
            )


def main():
    initialize_database()
    apply_theme()
    show_save_notification()

    with st.sidebar:
        st.markdown("### ♡ Soft Touch")
        st.caption("WELLNESS STUDIO")
        navigation = [
            ("Discover", ":material/spa:"),
            ("Private collection", ":material/favorite:"),
            ("About", ":material/info:"),
            ("FAQ", ":material/help:"),
            ("Contact", ":material/chat:"),
            ("Studio admin", ":material/settings:"),
        ]
        active_page = st.session_state.get("active_page", "Discover")
        for page_name, page_icon in navigation:
            if st.button(
                page_name,
                icon=page_icon,
                type="primary" if active_page == page_name else "secondary",
                use_container_width=True,
                key=f"navigation_{page_name.lower().replace(' ', '_')}",
            ):
                st.session_state.active_page = page_name
                st.rerun()
        page = st.session_state.get("active_page", "Discover")
        st.divider()
        st.caption("A considered moment, made personal.")
        st.divider()
        st.toggle("Dark mode", key="dark_mode", help="Switch the app to its dark color theme.")

    render_time_greeting()

    if page == "Studio admin":
        render_admin()
        return

    if page == "About":
        render_about()
        return
    if page == "FAQ":
        render_faq()
        return
    if page == "Contact":
        render_contact()
        return

    if not st.session_state.get("soft_touch_is_adult"):
        st.markdown('<div class="section-label">Before you continue</div>', unsafe_allow_html=True)
        st.markdown("## A private, adults-only experience")
        st.write("Please confirm that you are at least 18 years old to view the studio directory.")
        consent = st.checkbox("I confirm that I am 18 or older.")
        if st.button("Continue", disabled=not consent, icon=":material/favorite:"):
            st.session_state.soft_touch_is_adult = True
            st.rerun()
        return

    if page == "Discover":
        render_discover()
    else:
        render_vip()


if __name__ == "__main__":
    main()