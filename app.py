import base64
from datetime import datetime
import pandas as pd
import streamlit as st
from supabase_client import supabase

# =========================
# PAGE CONFIG
# =========================
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
    return email.strip().lower().endswith("@ohio.edu")


def get_user_profile(user_id: str):
    result = supabase.table("users").select("*").eq("id", user_id).execute().data
    return result[0] if result else None


def ensure_profile_exists(auth_user, full_name=None, student_id=None, role="student"):
    existing = get_user_profile(auth_user.id)
    if existing:
        return existing

    payload = {
        "id": auth_user.id,
        "full_name": full_name or auth_user.email.split("@")[0],
        "email": auth_user.email,
        "role": role,
        "student_id": student_id
    }
    supabase.table("users").insert(payload).execute()
    return get_user_profile(auth_user.id)


def signup_user(email, password, full_name, student_id):
    if not is_ohio_email(email):
        raise ValueError("Use your Ohio University email ending with @ohio.edu.")

    auth_response = supabase.auth.sign_up({
        "email": email,
        "password": password
    })

    auth_user = auth_response.user
    if auth_user is None:
        raise ValueError("Signup did not return a user. Check Supabase Auth settings.")

    ensure_profile_exists(
        auth_user,
        full_name=full_name,
        student_id=student_id,
        role="student"
    )
    return auth_user


def login_user(email, password):
    auth_response = supabase.auth.sign_in_with_password({
        "email": email,
        "password": password
    })

    auth_user = auth_response.user
    if auth_user is None:
        raise ValueError("Login failed.")

    profile = get_user_profile(auth_user.id)
    if profile is None:
        profile = ensure_profile_exists(
            auth_user,
            full_name=auth_user.email.split("@")[0],
            role="student"
        )

    st.session_state["auth_user_id"] = auth_user.id
    st.session_state["auth_email"] = auth_user.email
    st.session_state["profile"] = profile


def logout_user():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass

    for key in ["auth_user_id", "auth_email", "profile"]:
        if key in st.session_state:
            del st.session_state[key]


def load_users():
    return supabase.table("users").select("*").execute().data


def load_courses():
    return supabase.table("courses").select("*").execute().data


def load_attendance():
    return supabase.table("attendance").select("*").execute().data


def get_or_create_course(course_code, course_title):
    response = (
        supabase.table("courses")
        .select("*")
        .eq("course_code", course_code)
        .eq("course_title", course_title)
        .execute()
    )

    if response.data:
        return response.data[0]["id"]

    new_course = supabase.table("courses").insert({
        "course_code": course_code,
        "course_title": course_title
    }).execute()

    return new_course.data[0]["id"]


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


def add_check_in(student_id, course_id, checked_in_by="self"):
    now = get_now()
    payload = {
        "user_id": student_id,
        "course_id": course_id,
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


def log_admin_action(admin_user_id, target_user_id, course_id, action_type, notes):
    payload = {
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
    </style>
    """,
    unsafe_allow_html=True
)

# =========================
# AUTH SCREEN
# =========================
if "auth_user_id" not in st.session_state:
    st.markdown(
        """
        <div class="hero-box">
            <h1 style="font-size: 3.5rem; margin-bottom: 0.35rem;">OHIO UNIVERSITY</h1>
            <h3 style="margin-top: 0;">Attendance Management System</h3>
            <p class="small-note">
                Sign up with your Ohio University email, then log in to access attendance features.
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

        if st.button("Log In"):
            try:
                login_user(login_email, login_password)
                st.success("Login successful.")
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")
        st.markdown("</div>", unsafe_allow_html=True)

    with signup_tab:
        st.markdown('<div class="section-box">', unsafe_allow_html=True)
        st.subheader("Student Sign Up")
        signup_name = st.text_input("Full Name", key="signup_name")
        signup_student_id = st.text_input("Student ID", key="signup_student_id")
        signup_email = st.text_input("Ohio University Email", key="signup_email")
        signup_password = st.text_input("Create Password", type="password", key="signup_password")

        if st.button("Create Student Account"):
            try:
                signup_user(
                    email=signup_email,
                    password=signup_password,
                    full_name=signup_name,
                    student_id=signup_student_id
                )
                st.success("Account created. You can now log in.")
            except Exception as e:
                st.error(f"Signup failed: {e}")
        st.markdown("</div>", unsafe_allow_html=True)

    st.stop()

# =========================
# CURRENT USER
# =========================
current_profile = st.session_state.get("profile")
current_user_id = st.session_state.get("auth_user_id")
current_role = safe_lower(current_profile.get("role")) if current_profile else "student"

# =========================
# LOAD DATA
# =========================
users = load_users()
courses = load_courses()
attendance = load_attendance()
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
st.sidebar.markdown("---")

nav_options = ["Dashboard", "Check In / Check Out"]
if current_role == "admin":
    nav_options += ["Admin Dashboard", "Current Class", "Attendance Records", "Analytics"]

page = st.sidebar.radio("Navigation", nav_options)
st.sidebar.markdown("---")

if st.sidebar.button("Log Out"):
    logout_user()
    st.rerun()

# =========================
# HEADER
# =========================
st.markdown(
    """
    <div class="hero-box">
        <h1 style="font-size: 3.5rem; margin-bottom: 0.35rem;">OHIO UNIVERSITY</h1>
        <h3 style="margin-top: 0;">Attendance Management System</h3>
        <p class="small-note">
            Secure attendance tracking with student check-in, check-out, and administrator oversight.
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

# =========================
# DASHBOARD
# =========================
if page == "Dashboard":
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("My Dashboard")
    st.write(f"**Name:** {current_profile.get('full_name', '')}")
    st.write(f"**Role:** {current_profile.get('role', '')}")
    st.write(f"**Student ID:** {current_profile.get('student_id', '')}")
    if current_role == "admin":
        st.success("Administrator access is active.")
    st.markdown("</div>", unsafe_allow_html=True)

# =========================
# CHECK IN / CHECK OUT
# =========================
elif page == "Check In / Check Out":
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Attendance Action Panel")

    course_code = st.text_input("Enter Course Code (e.g., EDRE 7200)")
    course_title = st.text_input("Enter Course Title (e.g., Item Analysis)")

    selected_course_id = None
    if course_code and course_title:
        selected_course_id = get_or_create_course(course_code.strip(), course_title.strip())

    active_record = None
    if selected_course_id:
        active_record = get_active_record(attendance, current_user_id, selected_course_id, today)

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Check In"):
            if not course_code or not course_title:
                st.warning("Enter both course code and course title.")
            elif active_record:
                st.warning("You already have an active check-in for this course today.")
            else:
                add_check_in(current_user_id, selected_course_id, checked_in_by="self")
                st.success("Checked in successfully.")
                st.rerun()

    with col2:
        if st.button("Check Out"):
            if not course_code or not course_title:
                st.warning("Enter both course code and course title.")
            elif not active_record:
                st.warning("No active check-in found for this course today.")
            else:
                add_check_out(active_record["id"], checked_out_by="self")
                st.success("Checked out successfully.")
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# =========================
# ADMIN DASHBOARD
# =========================
elif page == "Admin Dashboard":
    if current_role != "admin":
        st.error("Access denied.")
        st.stop()

    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Administrator Dashboard")

    col1, col2, col3 = st.columns(3)
    with col1:
        metric_card("Students Currently In Class", len(current_in_class_df))
    with col2:
        today_total = 0 if attendance_df.empty else len(attendance_df[attendance_df["Attendance Date"] == today])
        metric_card("Today’s Attendance Records", today_total)
    with col3:
        metric_card("Registered Students", len(students))

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Manual Student Check-Out")

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
                admin_user_id=current_user_id,
                target_user_id=target_user_id,
                course_id=course_id,
                action_type="manual_check_out",
                notes="Administrator manually checked out a student."
            )
            st.success("Student checked out by administrator.")
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# =========================
# CURRENT CLASS
# =========================
elif page == "Current Class":
    if current_role != "admin":
        st.error("Access denied.")
        st.stop()

    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("Students Currently In Class")
    st.write(f"**Current Count:** {len(current_in_class_df)}")

    display_df = current_in_class_df.drop(columns=["Attendance ID", "user_id", "course_id"], errors="ignore")
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

# =========================
# ATTENDANCE RECORDS
# =========================
elif page == "Attendance Records":
    if current_role != "admin":
        st.error("Access denied.")
        st.stop()

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
            file_name=f"ohio_attendance_{today}.csv",
            mime="text/csv"
        )
    st.markdown("</div>", unsafe_allow_html=True)

# =========================
# ANALYTICS
# =========================
elif page == "Analytics":
    if current_role != "admin":
        st.error("Access denied.")
        st.stop()

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