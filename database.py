from supabase_client import supabase

def get_or_create_course(course_code, course_title):
    # Check if course exists
    response = supabase.table("courses") \
        .select("*") \
        .eq("course_code", course_code) \
        .eq("course_title", course_title) \
        .execute()

    if response.data:
        return response.data[0]["id"]

    # Create new course
    new_course = supabase.table("courses").insert({
        "course_code": course_code,
        "course_title": course_title
    }).execute()

    return new_course.data[0]["id"]