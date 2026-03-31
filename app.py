import base64
import random
import string
from datetime import datetime

import pandas as pd
import streamlit as st
from supabase_client import supabase

st.set_page_config(
    page_title="Ohio University Attendance App",
    page_icon="✅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================
# HELPERS
# =========================
def get_base64_image(image_path: str) -> str:
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()


def safe_lower(value):
    return str(value).strip().lower() if value is not None else ""


def get_now():
    return datetime.now()


def is_ohio_email(email: str) -> bool:
    email = str(email).strip().lower()
    return "@" in email and email.endswith("@ohio.edu")


def generate_class_code(length=8):
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))

def get_org_name(org_id):
    try:
        response = supabase.table("organizations").select("name").eq("id", org_id).execute()
        if response.data:
            return response.data[0]["name"]
        return "Unknown"
    except Exception as e:
        return "Error"

def get_organizations():
    response = supabase.table("organizations").select("*").order("name").execute()
    return response.data if response.data else []


def get_user_profile(user_id: str):
    response = supabase.table("users").select("*").eq("id", user_id).execute()
    return response.data[0] if response.data else None


def get_user_profile_by_email(email: str):
    response = (
        supabase.table("users")
        .select("*")
        .eq("email", email.strip().lower())
        .execute()
    )
    return response.data[0] if response.data else None


def ensure_profile_exists(auth_user, full_name=None, student_id=None, role="student", organization_id=None):
    existing = get_user_profile(auth_user.id)
    if existing:
        return existing

    existing_by_email = get_user_profile_by_email(auth_user.email)
    if existing_by_email:
        return existing_by_email

    payload = {
        "id": auth_user.id,
        "organization_id": organization_id,
        "full_name": full_name or auth_user.email.split("@")[0],
        "email": auth_user.email.strip().lower(),
        "role": role,
        "student_id": student_id
    }

    insert_response = supabase.table("users").insert(payload).execute()
    if not insert_response.data:
        return None

    return get_user_profile(auth_user.id)


def signup_user(email, password, full_name, student_id, organization_id):
    email = str(email).strip().lower()
    password = str(password).strip()
    full_name = str(full_name).strip()
    student_id = str(student_id).strip()

    if not full_name:
        st.error("Enter your full name.")
        return None

    if not student_id:
        st.error("Enter your student ID.")
        return None

    if not organization_id:
        st.error("Choose an organization.")
        return None

    if not is_ohio_email(email):
        st.error("Use your Ohio University email ending with @ohio.edu.")
        return None

    if len(password) < 6:
        st.error("Password must be at least 6 characters.")
        return None

    existing_profile = get_user_profile_by_email(email)
    if existing_profile:
        st.warning("An account profile with this email already exists. Try logging in instead.")
        return None

    try:
        auth_response = supabase.auth.sign_up({
            "email": email,
            "password": password
        })

        auth_user = getattr(auth_response, "user", None)
        if auth_user is None:
            st.error("Signup failed. No authentication user was created.")
            return None

        profile_response = supabase.table("users").insert({
            "id": auth_user.id,
            "full_name": full_name,
            "student_id": student_id,
            "email": email,
            "organization_id": organization_id,
            "role": "student"
        }).execute()

        if not profile_response.data:
            st.error("User profile creation failed. The login cannot work until the profile is saved.")
            return None

        return auth_response

    except Exception as e:
        st.error(f"Signup failed: {e}")
        return None


def login_user(email, password):
    email = str(email).strip().lower()
    password = str(password).strip()

    if not is_ohio_email(email):
        st.error("Use your Ohio University email ending with @ohio.edu.")
        return None

    if not password:
        st.error("Enter your password.")
        return None

    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        auth_user = getattr(auth_response, "user", None)
        if auth_user is None:
            st.error("Login failed. Invalid email or password.")
            return None

        profile = get_user_profile(auth_user.id)

        if profile is None:
            profile = get_user_profile_by_email(email)

        if profile is None:
            profile = ensure_profile_exists(auth_user)

        if profile is None:
            st.error("Login failed: User profile not found in users table.")
            return None

        st.session_state["auth_user_id"] = auth_user.id
        st.session_state["auth_email"] = auth_user.email
        st.session_state["profile"] = profile

        return profile

    except Exception as e:
        st.error(f"Login failed: {e}")
        return None


def logout_user():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass

    for key in ["auth_user_id", "auth_email", "profile"]:
        if key in st.session_state:
            del st.session_state[key]


def load_org_users(org_id):
    response = supabase.table("users").select("*").eq("organization_id", org_id).execute()
    return response.data if response.data else []


def load_org_courses(org_id):
    response = supabase.table("courses").select("*").eq("organization_id", org_id).execute()
    return response.data if response.data else []


def load_org_class_codes(org_id):
    response = supabase.table("class_codes").select("*").eq("organization_id", org_id).execute()
    return response.data if response.data else []


def load_org_attendance(org_id):
    response = supabase.table("attendance").select("*").eq("organization_id", org_id).execute()
    return response.data if response.data else []


def get_or_create_course(org_id, course_code, course_title):
    response = (
        supabase.table("courses")
        .select("*")
        .eq("organization_id", org_id)
        .eq("course_code", course_code)
        .eq("course_title", course_title)
        .execute()
    )

    if response.data:
        return response.data[0]

    new_course = supabase.table("courses").insert({
        "organization_id": org_id,
        "course_code": course_code,
        "course_title": course_title
    }).execute()

    return new_course.data[0] if new_course.data else None


def get_today_code_for_course(org_id, course_id, today):
    response = (
        supabase.table("class_codes")
        .select("*")
        .eq("organization_id", org_id)
        .eq("course_id", course_id)
        .eq("active_date", today)
        .execute()
    )
    return response.data[0] if response.data else None


def create_or_replace_daily_code(org_id, course_id, admin_user_id, custom_code=None):
    today = get_now().date().isoformat()
    code_value = custom_code.strip().upper() if custom_code else generate_class_code()

    existing = get_today_code_for_course(org_id, course_id, today)

    if existing:
        updated = (
            supabase.table("class_codes")
            .update({
                "code": code_value,
                "created_by": admin_user_id
            })
            .eq("id", existing["id"])
            .execute()
        )
        return updated.data[0] if updated.data else None

    created = supabase.table("class_codes").insert({
        "organization_id": org_id,
        "course_id": course_id,
        "code": code_value,
        "active_date": today,
        "created_by": admin_user_id
    }).execute()

    return created.data[0] if created.data else None


def find_course_by_class_code(org_id, class_code, today):
    code_match = (
        supabase.table("class_codes")
        .select("*")
        .eq("organization_id", org_id)
        .eq("code", class_code.strip().upper())
        .eq("active_date", today)
        .execute()
    )

    if not code_match.data:
        return None

    class_code_row = code_match.data[0]
    course_id = class_code_row["course_id"]

    course_match = (
        supabase.table("courses")
        .select("*")
        .eq("id", course_id)
        .eq("organization_id", org_id)
        .execute()
    )

    if not course_match.data:
        return None

    return {
        "class_code": class_code_row,
        "course": course_match.data[0]
    }


def get_active_record(attendance, student_id, course_id, today):
    for record in attendance:
        if (
            record.get("user_id") == student_id
            and record.get("course_id") == course_id
            and record.get("attendance_date") == today
            and record.get("check_out_time") is None
        ):
            return record
    return None


def add_check_in(org_id, student_id, course_id, class_code_id, checked_in_by="self"):
    now = get_now()
    payload = {
        "organization_id": org_id,
        "user_id": student_id,
        "course_id": course_id,
        "class_code_id": class_code_id,
        "attendance_date": now.date().isoformat(),
        "check_in_time": now.isoformat(),
        "status": "checked_in",
        "checked_in_by": checked_in_by
    }
    supabase.table("attendance").insert(payload).execute()


def add_check_out(attendance_id, checked_out_by="self"):
    now = get_now()
    payload = {
        "check_out_time": now.isoformat(),
        "status": "checked_out",
        "checked_out_by": checked_out_by
    }
    supabase.table("attendance").update(payload).eq("id", attendance_id).execute()


def log_admin_action(org_id, admin_user_id, target_user_id, course_id, action_type, notes):
    payload = {
        "organization_id": org_id,
        "admin_user_id": admin_user_id,
        "target_user_id": target_user_id,
        "course_id": course_id,
        "action_type": action_type,
        "notes": notes
    }
    supabase.table("admin_actions").insert(payload).execute()


def build_lookup_maps(users, courses):
    user_map = {
        u["id"]: {
            "full_name": u.get("full_name", "Unknown User"),
            "email": u.get("email", ""),
            "role": u.get("role", ""),
            "student_id": u.get("student_id", "")
        }
        for u in users
    }

    course_map = {
        c["id"]: {
            "course_code": c.get("course_code", ""),
            "course_title": c.get("course_title", "")
        }
        for c in courses
    }

    return user_map, course_map


def enrich_attendance(attendance, user_map, course_map):
    rows = []
    for record in attendance:
        user_info = user_map.get(record.get("user_id"), {})
        course_info = course_map.get(record.get("course_id"), {})

        rows.append({
            "Attendance ID": record.get("id"),
            "Student Name": user_info.get("full_name", "Unknown"),
            "Student ID": user_info.get("student_id", ""),
            "Email": user_info.get("email", ""),
            "Course Code": course_info.get("course_code", ""),
            "Course Title": course_info.get("course_title", ""),
            "Attendance Date": record.get("attendance_date"),
            "Check In Time": record.get("check_in_time"),
            "Check Out Time": record.get("check_out_time"),
            "Status": record.get("status"),
            "Checked In By": record.get("checked_in_by"),
            "Checked Out By": record.get("checked_out_by"),
            "Created At": record.get("created_at"),
            "user_id": record.get("user_id"),
            "course_id": record.get("course_id"),
        })
    return rows


def metric_card(label, value):
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


# =========================
# STYLING
# =========================
background_base64 = get_base64_image("assets/background.jpg")

st.markdown(
    f"""
    <style>
    [data-testid="stSidebarNav"] {{
        display: none;
    }}

    .stApp {{
        background-image:
            linear-gradient(rgba(5, 45, 34, 0.84), rgba(5, 45, 34, 0.84)),
            url("data:image/jpg;base64,{background_base64}");
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }}

    section[data-testid="stSidebar"] {{
        background: rgba(2, 28, 21, 0.97);
        border-right: 1px solid rgba(255,255,255,0.08);
    }}

    section[data-testid="stSidebar"] * {{
        color: white !important;
    }}

    .block-container {{
        padding-top: 2rem;
        padding-bottom: 2rem;
    }}

    h1, h2, h3, h4, h5, h6, p, label, div {{
        color: white;
    }}

    .hero-box {{
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.14);
        backdrop-filter: blur(10px);
        border-radius: 20px;
        padding: 2rem;
        margin-bottom: 1.2rem;
        box-shadow: 0 8px 30px rgba(0,0,0,0.28);
    }}

    .section-box {{
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.12);
        backdrop-filter: blur(8px);
        border-radius: 18px;
        padding: 1.5rem;
        margin-top: 1rem;
        margin-bottom: 1rem;
    }}

    .metric-card {{
        background: rgba(255,255,255,0.10);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 16px;
        padding: 1rem;
        text-align: center;
        min-height: 105px;
    }}

    .metric-label {{
        font-size: 0.95rem;
        opacity: 0.9;
        margin-bottom: 0.25rem;
    }}

    .metric-value {{
        font-size: 2rem;
        font-weight: 700;
    }}

    div.stButton > button {{
        border-radius: 12px;
        padding: 0.75rem 1rem;
        font-weight: 600;
        border: none;
        width: 100%;
        background: linear-gradient(135deg, #1f7a5a, #145c43);
        color: white;
    }}

    div.stButton > button:hover {{
        opacity: 0.92;
        color: white;
    }}

    div[data-testid="stDataFrame"] {{
        background: rgba(255,255,255,0.97);
        border-radius: 14px;
        padding: 0.35rem;
    }}

    .small-note {{
        color: #d9efe5;
        font-size: 0.95rem;
    }}

    /* Green text for selectbox options */
    div[data-baseweb="select"] span {{
        color: #2ecc71 !important;
        font-weight: 600;
    }}

    div[data-baseweb="popover"] li {{
        color: #1a7a4a !important;
        font-weight: 500;
    }}

    div[data-baseweb="popover"] li:hover {{
        background-color: rgba(46, 204, 113, 0.15) !important;
        color: #145c43 !important;
    }}
    </style>
    """,
    unsafe_allow_html=True
)

# =========================
# AUTH SCREEN
# =========================
if "auth_user_id" not in st.session_state:
    orgs = get_organizations()
    org_options = {org["name"]: org["id"] for org in orgs}

    st.markdown(
        """
        <div class="hero-box">
            <h1 style="font-size: 3.5rem; margin-bottom: 0.35rem;">OHIO UNIVERSITY</h1>
            <h3 style="margin-top: 0;">Attendance Management System</h3>
            <p class="small-note">
                Sign up with your Ohio University email, choose your organization, and use a daily class code to check in.
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    login_tab, signup_tab = st.tabs(["Login", "Sign Up"])

    with login_tab:
        st.markdown('<div class="section-box">', unsafe_allow_html=True)
        st.subheader("Login")
        login_email = st.text_input("Ohio University Email", key="login_email")
        login_password = st.text_input("Password", type="password", key="login_password")

        if st.button("Log In", key="login_button"):
            profile = login_user(login_email, login_password)
            if profile:
                st.success("Login successful.")
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    with signup_tab:
        st.markdown('<div class="section-box">', unsafe_allow_html=True)
        st.subheader("Student Sign Up")
        signup_name = st.text_input("Full Name", key="signup_name")
        signup_student_id = st.text_input("Student ID", key="signup_student_id")
        signup_email = st.text_input("Ohio University Email", key="signup_email")
        signup_password = st.text_input("Create Password", type="password", key="signup_password")

        if org_options:
            signup_org_name = st.selectbox("Choose Organization", list(org_options.keys()), key="signup_org")
            selected_org_id = org_options[signup_org_name]
        else:
            signup_org_name = None
            selected_org_id = None
            st.warning("No organizations found. Add organizations in Supabase first.")

        if st.button("Create Student Account", key="signup_button"):
            auth_response = signup_user(
                email=signup_email,
                password=signup_password,
                full_name=signup_name,
                student_id=signup_student_id,
                organization_id=selected_org_id
            )
            if auth_response:
                st.success("Account created. You can now log in.")

        st.markdown("</div>", unsafe_allow_html=True)

    st.stop()

# =========================
# CURRENT USER + ORG
# =========================
current_profile = st.session_state.get("profile")
current_user_id = st.session_state.get("auth_user_id")

if not current_profile:
    st.error("User profile is missing. Please log in again.")
    st.stop()

current_role = safe_lower(current_profile.get("role"))
current_org_id = current_profile.get("organization_id")

if not current_org_id:
    st.error(
        "Your account is not linked to an organization yet. "
        "Please contact the administrator or update your user row in Supabase."
    )
    st.stop()

# Resolve org name from Supabase
current_org_name = get_org_name(current_org_id)

# =========================
# LOAD ORG DATA
# =========================
users = load_org_users(current_org_id)
courses = load_org_courses(current_org_id)
class_codes = load_org_class_codes(current_org_id)
attendance = load_org_attendance(current_org_id)

user_map, course_map = build_lookup_maps(users, courses)
attendance_rows = enrich_attendance(attendance, user_map, course_map)
attendance_df = pd.DataFrame(attendance_rows)

students = [u for u in users if safe_lower(u.get("role")) == "student"]
today = get_now().date().isoformat()

if attendance_df.empty:
    current_in_class_df = pd.DataFrame(columns=[
        "Student Name", "Student ID", "Course Code", "Course Title",
        "Attendance Date", "Check In Time", "Status"
    ])
else:
    current_in_class_df = attendance_df[
        (attendance_df["Attendance Date"] == today) &
        (attendance_df["Check Out Time"].isna())
    ][[
        "Student Name", "Student ID", "Course Code", "Course Title",
        "Attendance Date", "Check In Time", "Status", "Attendance ID", "user_id", "course_id"
    ]]

# =========================
# SIDEBAR
# =========================
st.sidebar.markdown("## Ohio University")
st.sidebar.markdown("### Attendance App")
st.sidebar.markdown("---")
st.sidebar.write(f"**Logged in as:** {current_profile.get('full_name', '')}")
st.sidebar.write(f"**Role:** {current_profile.get('role', '')}")
st.sidebar.write(f"**Organization:** {current_org_name}")
st.sidebar.markdown("---")

if current_role == "admin":
    nav_options = [
        "Admin Dashboard",
        "Create Daily Class Code",
        "Current Class",
        "Attendance Records",
        "Analytics"
    ]
else:
    nav_options = ["Check In", "Check Out"]

page = st.sidebar.radio("Navigation", nav_options)
st.sidebar.markdown("---")

if st.sidebar.button("Log Out"):
    logout_user()
    st.rerun()

# =========================
# HEADER
# =========================
st.markdown(
    f"""
    <div class="hero-box">
        <h1 style="font-size: 3.5rem; margin-bottom: 0.35rem;">OHIO UNIVERSITY</h1>
        <h3 style="margin-top: 0;">Attendance Management System</h3>
        <p class="small-note">
            Organization: {current_org_name}
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

# =========================
# CHECK IN PAGE
# =========================
if page == "Check In":
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("✅ Check In Using Daily Class Code")

    class_code_input = st.text_input("Enter Today's Class Code", key="checkin_code_input").strip().upper()

    matched = None
    if class_code_input:
        matched = find_course_by_class_code(current_org_id, class_code_input, today)

    if class_code_input and not matched:
        st.warning("Invalid class code for today.")

    if matched:
        matched_course = matched["course"]
        matched_class_code = matched["class_code"]

        st.success(f"Class found: {matched_course['course_code']} - {matched_course['course_title']}")

        active_record = get_active_record(
            attendance,
            current_user_id,
            matched_course["id"],
            today
        )

        if st.button("Check In", key="checkin_btn"):
            if active_record:
                st.warning("You are already checked in for this class today.")
            else:
                add_check_in(
                    current_org_id,
                    current_user_id,
                    matched_course["id"],
                    matched_class_code["id"],
                    checked_in_by="self"
                )
                st.success("Checked in successfully.")
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# =========================
# CHECK OUT PAGE
# =========================
elif page == "Check Out":
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("🚪 Check Out Using Daily Class Code")

    class_code_input = st.text_input("Enter Today's Class Code", key="checkout_code_input").strip().upper()

    matched = None
    if class_code_input:
        matched = find_course_by_class_code(current_org_id, class_code_input, today)

    if class_code_input and not matched:
        st.warning("Invalid class code for today.")

    if matched:
        matched_course = matched["course"]

        st.success(f"Class found: {matched_course['course_code']} - {matched_course['course_title']}")

        active_record = get_active_record(
            attendance,
            current_user_id,
            matched_course["id"],
            today
        )

        if st.button("Check Out", key="checkout_btn"):
            if not active_record:
                st.warning("No active check-in found for this class.")
            else:
                add_check_out(active_record["id"], checked_out_by="self")
                st.success("Checked out successfully.")
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# =========================
# ADMIN PAGES
# =========================
elif page == "Admin Dashboard":
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Administrator Dashboard")

    col1, col2, col3 = st.columns(3)
    with col1:
        metric_card("Students Currently In Class", len(current_in_class_df))
    with col2:
        today_total = 0 if attendance_df.empty else len(attendance_df[attendance_df["Attendance Date"] == today])
        metric_card("Today's Attendance Records", today_total)
    with col3:
        metric_card("Registered Students", len(students))
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Today's Class Codes")

    today_codes_rows = []
    for code_row in class_codes:
        if code_row.get("active_date") == today:
            c = course_map.get(code_row.get("course_id"), {})
            today_codes_rows.append({
                "Course Code": c.get("course_code", ""),
                "Course Title": c.get("course_title", ""),
                "Daily Code": code_row.get("code", "")
            })

    if today_codes_rows:
        st.dataframe(pd.DataFrame(today_codes_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No daily class codes have been created yet.")
    st.markdown("</div>", unsafe_allow_html=True)

elif page == "Create Daily Class Code":
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Create or Replace Daily Class Code")

    course_code_input = st.text_input("Course Code (e.g., EDRE 7200)")
    course_title_input = st.text_input("Course Title (e.g., Item Analysis)")
    custom_code_input = st.text_input("Optional Custom Code (leave blank to auto-generate)").strip().upper()

    if st.button("Create Today's Code"):
        if not course_code_input or not course_title_input:
            st.warning("Enter both course code and course title.")
        else:
            course_row = get_or_create_course(
                current_org_id,
                course_code_input.strip(),
                course_title_input.strip()
            )

            if not course_row:
                st.error("Could not create or load the course.")
            else:
                created_code = create_or_replace_daily_code(
                    current_org_id,
                    course_row["id"],
                    current_user_id,
                    custom_code=custom_code_input if custom_code_input else None
                )

                if created_code:
                    st.success(f"Today's class code is: {created_code['code']}")
                    st.rerun()
                else:
                    st.error("Could not create the daily class code.")

    st.markdown("</div>", unsafe_allow_html=True)

elif page == "Current Class":
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Students Currently In Class")
    st.write(f"**Current Count:** {len(current_in_class_df)}")

    display_df = current_in_class_df.drop(columns=["Attendance ID", "user_id", "course_id"], errors="ignore")
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Administrator Manual Check-Out")

    active_student_options = {}
    for row in current_in_class_df.to_dict("records"):
        label = f"{row['Student Name']} | {row['Course Code']} | {row['Course Title']}"
        active_student_options[label] = row

    if not active_student_options:
        st.info("No students are currently checked in.")
    else:
        selected_active_label = st.selectbox(
            "Select Student to Check Out",
            list(active_student_options.keys())
        )

        if st.button("Administrator Check Out Student"):
            selected_row = active_student_options[selected_active_label]
            attendance_id = selected_row["Attendance ID"]
            target_user_id = selected_row["user_id"]
            course_id = selected_row["course_id"]

            add_check_out(attendance_id, checked_out_by="admin")
            log_admin_action(
                current_org_id,
                current_user_id,
                target_user_id,
                course_id,
                "manual_check_out",
                "Administrator manually checked out a student."
            )
            st.success("Student checked out by administrator.")
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

elif page == "Attendance Records":
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Attendance Records")

    if attendance_df.empty:
        st.info("No attendance records found.")
    else:
        display_columns = [
            "Student Name", "Student ID", "Course Code", "Course Title",
            "Attendance Date", "Check In Time", "Check Out Time", "Status",
            "Checked In By", "Checked Out By"
        ]
        st.dataframe(attendance_df[display_columns], use_container_width=True, hide_index=True)

        csv_data = attendance_df[display_columns].to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download Attendance CSV",
            data=csv_data,
            file_name=f"{current_org_name.lower().replace(' ', '_')}_attendance_{today}.csv",
            mime="text/csv"
        )
    st.markdown("</div>", unsafe_allow_html=True)

elif page == "Analytics":
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Attendance Analytics")

    if attendance_df.empty:
        st.info("No attendance data available.")
    else:
        by_course = (
            attendance_df.groupby("Course Code")
            .size()
            .reset_index(name="Attendance Count")
            .sort_values("Attendance Count", ascending=False)
        )
        st.write("### Attendance by Course")
        st.bar_chart(by_course.set_index("Course Code"))

        by_status = (
            attendance_df.groupby("Status")
            .size()
            .reset_index(name="Count")
        )
        st.write("### Attendance by Status")
        st.bar_chart(by_status.set_index("Status"))

    st.markdown("</div>", unsafe_allow_html=True)