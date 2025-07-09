import json
import os
from flask import Flask, render_template, request, redirect, url_for, flash
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.trace.status import Status, StatusCode
import logging

# Flask App Initialization
app = Flask(__name__)
app.secret_key = 'secret'
COURSE_FILE = 'course_catalog.json'

# OpenTelemetry Tracer Setup
resource = Resource(attributes={SERVICE_NAME: "CourseInfoPortal"})
provider = TracerProvider(resource=resource)
jaeger_exporter = JaegerExporter(agent_host_name="localhost", agent_port=6831)
provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

# Instrument Flask app
FlaskInstrumentor().instrument_app(app)

# Logging Configuration
file_handler = logging.FileHandler("app.log")
file_handler.setLevel(logging.INFO)  # Logs at INFO level and above (INFO, WARNING, ERROR, CRITICAL)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)  # Logs at DEBUG level and above

logging.basicConfig(
    level=logging.DEBUG,  # Global log level
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[file_handler, console_handler]
)


# Utility Functions
def load_courses():
   """Load courses from the JSON file."""
   if not os.path.exists(COURSE_FILE):
        return []  # Return an empty list if the file doesn't exist
   with open(COURSE_FILE, 'r') as file:
        return json.load(file)



def save_courses(data):
    """Save new course data to the JSON file."""
    courses = load_courses()  # Load existing courses
    courses.append(data)  # Append the new course
    with open(COURSE_FILE, 'w') as file:
        json.dump(courses, file, indent=4)


# Routes
@app.route('/')
def index():
    with tracer.start_as_current_span("Render index"):
        logging.info("Rendering index page")
        return render_template('index.html')


@app.route('/catalog')
def course_catalog():
    with tracer.start_as_current_span("Render course catalog"):
        courses = load_courses()
        logging.info("Rendering course catalog with %d courses", len(courses))
        return render_template('course_catalog.html', courses=courses)


@app.route('/course/<code>')
def course_details(code):
    with tracer.start_as_current_span("View course details", attributes={"course_code": code}):
        courses = load_courses()
        course = next((course for course in courses if course['code'] == code), None)
        if not course:
            logging.error("Course with code '%s' not found", code)
            flash(f"No course found with code '{code}'.", "error")
            return redirect(url_for('course_catalog'))
        logging.info("Displaying details for course: %s", course['name'])
        return render_template('course_details.html', course=course)


@app.route('/add', methods=['GET', 'POST'])
def add_course():
    with tracer.start_as_current_span("Add a course") as span:
        if request.method == 'POST':
            course_name = request.form.get('name')
            course_code = request.form.get('code')
            instructor = request.form.get('instructor')

            # Server-side validation for required fields
            missing_fields = []
            if not course_name:
                missing_fields.append("Course Name")
            if not course_code:
                missing_fields.append("Course Code")
            if not instructor:
                missing_fields.append("Instructor")

            if missing_fields:
                # Log the error in the app log and Jaeger
                error_message = f"Missing required fields: {', '.join(missing_fields)}"
                logging.error(error_message)
                span.set_status(Status(StatusCode.ERROR, description=error_message))  # Mark error in Jaeger trace
                
                # Flash error message to the user
                flash(f"Error: The following fields are required: {', '.join(missing_fields)}", "error")
                return redirect(url_for('add_course'))

            # Save the course if validation passes
            course_data = {
                "name": course_name,
                "code": course_code,
                "instructor": instructor,
                "semester": request.form.get('semester', ''),
                "schedule": request.form.get('schedule', ''),
                "classroom": request.form.get('classroom', ''),
                "prerequisites": request.form.get('prerequisites', 'None'),
                "grading": request.form.get('grading', 'Not specified'),
                "description": request.form.get('description', 'No description provided')
            }

            save_courses(course_data)
            logging.info("Added new course: %s", course_name)
            flash(f"Course '{course_name}' added successfully!", "success")
            return redirect(url_for('course_catalog'))

        # Render the form for adding a course
        logging.info("Rendering add course page")
        return render_template('add_course.html')


@app.route('/remove/<code>', methods=['POST'])
def remove_course(code):
    with tracer.start_as_current_span("Remove course", attributes={"course_code": code}):
        courses = load_courses()
        course_to_remove = next((course for course in courses if course['code'] == code), None)

        if course_to_remove:
            courses = [course for course in courses if course['code'] != code]
            with open(COURSE_FILE, 'w') as file:
                json.dump(courses, file, indent=4)
            logging.info("Removed course with code: %s", code)
            flash(f"Course '{course_to_remove['name']}' removed successfully!", "success")
        else:
            logging.error("Course with code '%s' not found for removal", code)
            flash(f"No course found with code '{code}'.", "error")

        return redirect(url_for('course_catalog'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
