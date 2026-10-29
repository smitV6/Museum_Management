import os
import datetime
from decimal import Decimal
import mysql.connector
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
# Secret key for flash messaging and session protection
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "museum_archive_secret_key_2025")

# Database Connection Configuration (matches existing MySQL database exactly)
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),  # Default to empty, falls back intelligently
    "database": os.environ.get("DB_NAME", "museum_management"),
}

def get_db_connection():
    """
    Establish and return a connection to the existing MySQL database.
    Attempts primary configuration and common local setups if auth fails.
    """
    configured_pwd = DB_CONFIG["password"]
    passwords_to_try = [
        configured_pwd,
        "",
        "YOUR_PASSWORD",
        "root",
        "admin",
        "1234",
        "123456",
        "mysql",
    ]
    seen = set()
    passwords = [p for p in passwords_to_try if not (p in seen or seen.add(p))]

    last_err = None
    for pwd in passwords:
        try:
            cfg = dict(DB_CONFIG)
            cfg["password"] = pwd
            conn = mysql.connector.connect(**cfg)
            return conn
        except mysql.connector.Error as err:
            last_err = err
            # Error 1045 is ER_ACCESS_DENIED_ERROR
            if getattr(err, "errno", None) != 1045:
                # If error is not auth (e.g. host unreachable or db not found), raise immediately
                raise err

    # If all passwords failed, raise the last auth error
    if last_err:
        raise last_err


@app.template_filter("format_date")
def format_date_filter(val):
    """Safely format dates whether datetime.date, datetime.datetime, or string."""
    if not val:
        return "—"
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val.strftime("%Y-%m-%d")
    return str(val)


@app.template_filter("format_price")
def format_price_filter(val):
    """Safely format decimal or float currency values."""
    if val is None:
        return "—"
    try:
        return f"{float(val):,.2f}"
    except (ValueError, TypeError):
        return str(val)


# ==============================================================================
# 0. DASHBOARD ROUTE
# ==============================================================================
@app.route("/")
def dashboard():
    """
    Dashboard presenting total counts of all entities in the museum_management
    database, quick management navigation, and recently cataloged artifacts.
    """
    stats = {
        "artifacts": 0,
        "museums": 0,
        "galleries": 0,
        "donors": 0,
        "curators": 0,
        "exhibitions": 0,
        "restorations": 0,
    }
    recent_artifacts = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS count FROM Artifacts")
        stats["artifacts"] = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) AS count FROM Museum")
        stats["museums"] = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) AS count FROM Gallery")
        stats["galleries"] = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) AS count FROM Donor")
        stats["donors"] = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) AS count FROM Curator")
        stats["curators"] = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) AS count FROM Exhibition")
        stats["exhibitions"] = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) AS count FROM Restoration_Department")
        stats["restorations"] = cursor.fetchone()["count"]

        recent_query = """
            SELECT 
                A.artifact_id,
                A.name,
                A.material,
                A.value,
                A.origin,
                A.age,
                G.name AS gallery_name,
                C.name AS curator_name
            FROM Artifacts A
            LEFT JOIN Gallery G ON A.gallery_id = G.gallery_id
            LEFT JOIN Curator C ON A.curator_id = C.curator_id
            ORDER BY A.artifact_id DESC
            LIMIT 5
        """
        cursor.execute(recent_query)
        recent_artifacts = cursor.fetchall()

        cursor.close()
        conn.close()
    except mysql.connector.Error as e:
        flash(f"Database connection error: {e}. Verify MySQL service is active.", "danger")

    return render_template(
        "dashboard.html",
        active_page="dashboard",
        stats=stats,
        recent_artifacts=recent_artifacts,
    )


# ==============================================================================
# 1. ARTIFACTS MODULE (CRUD + Search)
# ==============================================================================
@app.route("/artifacts")
def list_artifacts():
    """View and search artifacts joined with gallery, curator, donor, exhibition, and restoration."""
    search_query = request.args.get("q", "").strip()
    artifacts = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        base_query = """
            SELECT 
                A.artifact_id,
                A.name,
                A.material,
                A.value,
                A.origin,
                A.age,
                A.donor_id,
                A.curator_id,
                A.gallery_id,
                A.exhibition_id,
                A.restoration_id,
                D.name AS donor_name,
                C.name AS curator_name,
                G.name AS gallery_name,
                E.title AS exhibition_title,
                R.description_for_restoration AS restoration_desc,
                R.maintenance_cost AS restoration_cost
            FROM Artifacts A
            LEFT JOIN Donor D ON A.donor_id = D.donor_id
            LEFT JOIN Curator C ON A.curator_id = C.curator_id
            LEFT JOIN Gallery G ON A.gallery_id = G.gallery_id
            LEFT JOIN Exhibition E ON A.exhibition_id = E.exhibition_id
            LEFT JOIN Restoration_Department R ON A.restoration_id = R.restoration_id
        """

        if search_query:
            sql = (
                base_query
                + """
                WHERE A.name LIKE %s 
                   OR A.material LIKE %s 
                   OR A.origin LIKE %s
                   OR D.name LIKE %s
                   OR C.name LIKE %s
                   OR G.name LIKE %s
                   OR E.title LIKE %s
                ORDER BY A.artifact_id ASC
            """
            )
            wildcard = f"%{search_query}%"
            cursor.execute(
                sql,
                (
                    wildcard,
                    wildcard,
                    wildcard,
                    wildcard,
                    wildcard,
                    wildcard,
                    wildcard,
                ),
            )
        else:
            sql = base_query + " ORDER BY A.artifact_id ASC"
            cursor.execute(sql)

        artifacts = cursor.fetchall()
        cursor.close()
        conn.close()
    except mysql.connector.Error as e:
        flash(f"Error fetching artifacts: {e}", "danger")

    return render_template(
        "artifacts.html",
        active_page="artifacts",
        artifacts=artifacts,
        search_query=search_query,
    )


@app.route("/artifacts/add", methods=["GET", "POST"])
def add_artifact():
    """Register a new artifact record into the existing MySQL Artifacts table."""
    if request.method == "POST":
        try:
            artifact_id_str = request.form.get("artifact_id", "").strip()
            name = request.form.get("name", "").strip()
            material = request.form.get("material", "").strip() or None
            value_str = request.form.get("value", "").strip()
            origin = request.form.get("origin", "").strip() or None
            age_str = request.form.get("age", "").strip()

            donor_id_str = request.form.get("donor_id", "").strip()
            curator_id_str = request.form.get("curator_id", "").strip()
            gallery_id_str = request.form.get("gallery_id", "").strip()
            exhibition_id_str = request.form.get("exhibition_id", "").strip()
            restoration_id_str = request.form.get("restoration_id", "").strip()

            # Required field validation
            if not artifact_id_str or not name:
                flash("Artifact ID and Artifact Name are required fields.", "warning")
                return redirect(url_for("add_artifact"))

            artifact_id = int(artifact_id_str)
            value = float(value_str) if value_str else None
            age = int(age_str) if age_str else None

            donor_id = int(donor_id_str) if donor_id_str else None
            curator_id = int(curator_id_str) if curator_id_str else None
            gallery_id = int(gallery_id_str) if gallery_id_str else None
            exhibition_id = int(exhibition_id_str) if exhibition_id_str else None
            restoration_id = int(restoration_id_str) if restoration_id_str else None

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("SELECT artifact_id FROM Artifacts WHERE artifact_id = %s", (artifact_id,))
            if cursor.fetchone():
                flash(f"Artifact with ID #{artifact_id} already exists. Please choose a unique ID.", "warning")
                cursor.close()
                conn.close()
                return redirect(url_for("add_artifact"))

            insert_query = """
                INSERT INTO Artifacts 
                (artifact_id, name, material, value, origin, age, donor_id, curator_id, gallery_id, exhibition_id, restoration_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(
                insert_query,
                (
                    artifact_id,
                    name,
                    material,
                    value,
                    origin,
                    age,
                    donor_id,
                    curator_id,
                    gallery_id,
                    exhibition_id,
                    restoration_id,
                ),
            )
            conn.commit()
            cursor.close()
            conn.close()

            flash(f"Artifact '{name}' (ID #{artifact_id}) has been successfully cataloged into MySQL!", "success")
            return redirect(url_for("list_artifacts"))

        except ValueError as ve:
            flash(f"Invalid numeric input: {ve}", "danger")
            return redirect(url_for("add_artifact"))
        except mysql.connector.Error as e:
            flash(f"MySQL Error saving artifact: {e}", "danger")
            return redirect(url_for("add_artifact"))

    # GET: fetch lookup data for dropdown options
    donors = []
    curators = []
    galleries = []
    exhibitions = []
    restorations = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT donor_id, name FROM Donor ORDER BY name ASC")
        donors = cursor.fetchall()

        cursor.execute("SELECT curator_id, name, qualification FROM Curator ORDER BY name ASC")
        curators = cursor.fetchall()

        cursor.execute("SELECT gallery_id, name, floor_number FROM Gallery ORDER BY name ASC")
        galleries = cursor.fetchall()

        cursor.execute("SELECT exhibition_id, title FROM Exhibition ORDER BY title ASC")
        exhibitions = cursor.fetchall()

        cursor.execute(
            "SELECT restoration_id, description_for_restoration, date_catalog FROM Restoration_Department ORDER BY restoration_id DESC"
        )
        restorations = cursor.fetchall()

        cursor.close()
        conn.close()
    except mysql.connector.Error as e:
        flash(f"Error loading dropdown references: {e}", "warning")

    return render_template(
        "add_artifact.html",
        active_page="artifacts",
        donors=donors,
        curators=curators,
        galleries=galleries,
        exhibitions=exhibitions,
        restorations=restorations,
    )


@app.route("/artifacts/edit/<int:artifact_id>", methods=["GET", "POST"])
def edit_artifact(artifact_id):
    """Update an existing artifact record in the MySQL Artifacts table."""
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            material = request.form.get("material", "").strip() or None
            value_str = request.form.get("value", "").strip()
            origin = request.form.get("origin", "").strip() or None
            age_str = request.form.get("age", "").strip()

            donor_id_str = request.form.get("donor_id", "").strip()
            curator_id_str = request.form.get("curator_id", "").strip()
            gallery_id_str = request.form.get("gallery_id", "").strip()
            exhibition_id_str = request.form.get("exhibition_id", "").strip()
            restoration_id_str = request.form.get("restoration_id", "").strip()

            if not name:
                flash("Artifact Name is required.", "warning")
                return redirect(url_for("edit_artifact", artifact_id=artifact_id))

            value = float(value_str) if value_str else None
            age = int(age_str) if age_str else None

            donor_id = int(donor_id_str) if donor_id_str else None
            curator_id = int(curator_id_str) if curator_id_str else None
            gallery_id = int(gallery_id_str) if gallery_id_str else None
            exhibition_id = int(exhibition_id_str) if exhibition_id_str else None
            restoration_id = int(restoration_id_str) if restoration_id_str else None

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            update_query = """
                UPDATE Artifacts
                SET name = %s,
                    material = %s,
                    value = %s,
                    origin = %s,
                    age = %s,
                    donor_id = %s,
                    curator_id = %s,
                    gallery_id = %s,
                    exhibition_id = %s,
                    restoration_id = %s
                WHERE artifact_id = %s
            """
            cursor.execute(
                update_query,
                (
                    name,
                    material,
                    value,
                    origin,
                    age,
                    donor_id,
                    curator_id,
                    gallery_id,
                    exhibition_id,
                    restoration_id,
                    artifact_id,
                ),
            )
            conn.commit()
            cursor.close()
            conn.close()

            flash(f"Artifact #{artifact_id} ('{name}') was successfully updated in MySQL!", "success")
            return redirect(url_for("list_artifacts"))

        except ValueError as ve:
            flash(f"Invalid numeric input: {ve}", "danger")
            return redirect(url_for("edit_artifact", artifact_id=artifact_id))
        except mysql.connector.Error as e:
            flash(f"MySQL Error updating artifact: {e}", "danger")
            return redirect(url_for("edit_artifact", artifact_id=artifact_id))

    # GET: fetch artifact and dropdown data
    artifact = None
    donors = []
    curators = []
    galleries = []
    exhibitions = []
    restorations = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM Artifacts WHERE artifact_id = %s", (artifact_id,))
        artifact = cursor.fetchone()

        if not artifact:
            cursor.close()
            conn.close()
            flash(f"Artifact #{artifact_id} not found in database.", "danger")
            return redirect(url_for("list_artifacts"))

        cursor.execute("SELECT donor_id, name FROM Donor ORDER BY name ASC")
        donors = cursor.fetchall()

        cursor.execute("SELECT curator_id, name, qualification FROM Curator ORDER BY name ASC")
        curators = cursor.fetchall()

        cursor.execute("SELECT gallery_id, name, floor_number FROM Gallery ORDER BY name ASC")
        galleries = cursor.fetchall()

        cursor.execute("SELECT exhibition_id, title FROM Exhibition ORDER BY title ASC")
        exhibitions = cursor.fetchall()

        cursor.execute(
            "SELECT restoration_id, description_for_restoration, date_catalog FROM Restoration_Department ORDER BY restoration_id DESC"
        )
        restorations = cursor.fetchall()

        cursor.close()
        conn.close()
    except mysql.connector.Error as e:
        flash(f"Error loading artifact data: {e}", "danger")
        return redirect(url_for("list_artifacts"))

    return render_template(
        "edit_artifact.html",
        active_page="artifacts",
        artifact=artifact,
        donors=donors,
        curators=curators,
        galleries=galleries,
        exhibitions=exhibitions,
        restorations=restorations,
    )


@app.route("/artifacts/delete/<int:artifact_id>", methods=["POST"])
def delete_artifact(artifact_id):
    """Delete an artifact record directly from the MySQL Artifacts table."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("DELETE FROM Artifacts WHERE artifact_id = %s", (artifact_id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash(f"Artifact #{artifact_id} has been permanently deleted from MySQL.", "info")
    except mysql.connector.Error as e:
        flash(f"MySQL Error deleting artifact #{artifact_id}: {e}", "danger")

    return redirect(url_for("list_artifacts"))


# ==============================================================================
# 2. MUSEUMS MODULE (CRUD + Search)
# ==============================================================================
@app.route("/museums")
def list_museums():
    """List and search Museum records from the MySQL Museum table."""
    search_query = request.args.get("q", "").strip()
    museums = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if search_query:
            query = """
                SELECT * FROM Museum 
                WHERE name LIKE %s OR location LIKE %s OR contact_number LIKE %s
                ORDER BY museum_id ASC
            """
            wildcard = f"%{search_query}%"
            cursor.execute(query, (wildcard, wildcard, wildcard))
        else:
            cursor.execute("SELECT * FROM Museum ORDER BY museum_id ASC")

        museums = cursor.fetchall()
        cursor.close()
        conn.close()
    except mysql.connector.Error as e:
        flash(f"Error retrieving museums: {e}", "danger")

    return render_template(
        "museums.html",
        active_page="museums",
        museums=museums,
        search_query=search_query,
        edit_museum=None,
    )


@app.route("/museums/add", methods=["GET", "POST"])
def add_museum():
    """Insert a new museum record into the MySQL Museum table."""
    if request.method == "POST":
        try:
            museum_id = request.form.get("museum_id", "").strip()
            name = request.form.get("name", "").strip()
            location = request.form.get("location", "").strip() or None
            contact_number = request.form.get("contact_number", "").strip() or None

            if not museum_id or not name:
                flash("Museum ID and Name are required.", "warning")
                return redirect(url_for("list_museums"))

            museum_id = int(museum_id)

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("SELECT museum_id FROM Museum WHERE museum_id = %s", (museum_id,))
            if cursor.fetchone():
                flash(f"Museum with ID #{museum_id} already exists.", "warning")
                cursor.close()
                conn.close()
                return redirect(url_for("list_museums"))

            cursor.execute(
                "INSERT INTO Museum (museum_id, name, location, contact_number) VALUES (%s, %s, %s, %s)",
                (museum_id, name, location, contact_number),
            )
            conn.commit()
            cursor.close()
            conn.close()

            flash(f"Museum '{name}' (ID #{museum_id}) successfully added to MySQL!", "success")
        except ValueError:
            flash("Museum ID must be an integer.", "danger")
        except mysql.connector.Error as e:
            flash(f"MySQL Error inserting museum: {e}", "danger")

        return redirect(url_for("list_museums"))

    # If GET, redirect to the museums management page
    return redirect(url_for("list_museums"))


@app.route("/museums/edit/<int:museum_id>", methods=["GET", "POST"])
def edit_museum(museum_id):
    """View and update museum record in the MySQL Museum table."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            location = request.form.get("location", "").strip() or None
            contact_number = request.form.get("contact_number", "").strip() or None

            if not name:
                flash("Museum Name is required.", "warning")
                return redirect(url_for("edit_museum", museum_id=museum_id))

            cursor.execute(
                "UPDATE Museum SET name = %s, location = %s, contact_number = %s WHERE museum_id = %s",
                (name, location, contact_number, museum_id),
            )
            conn.commit()
            cursor.close()
            conn.close()

            flash(f"Museum #{museum_id} updated successfully in MySQL!", "success")
            return redirect(url_for("list_museums"))
        except mysql.connector.Error as e:
            flash(f"MySQL Error updating museum #{museum_id}: {e}", "danger")
            cursor.close()
            conn.close()
            return redirect(url_for("list_museums"))

    # GET: retrieve record and render page with edit prefill
    cursor.execute("SELECT * FROM Museum WHERE museum_id = %s", (museum_id,))
    target = cursor.fetchone()

    cursor.execute("SELECT * FROM Museum ORDER BY museum_id ASC")
    museums = cursor.fetchall()

    cursor.close()
    conn.close()

    if not target:
        flash(f"Museum #{museum_id} not found.", "warning")
        return redirect(url_for("list_museums"))

    return render_template(
        "museums.html",
        active_page="museums",
        museums=museums,
        search_query="",
        edit_museum=target,
    )


@app.route("/museums/delete/<int:museum_id>", methods=["POST"])
def delete_museum(museum_id):
    """Delete a museum record from the MySQL Museum table."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("DELETE FROM Museum WHERE museum_id = %s", (museum_id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash(f"Museum #{museum_id} deleted successfully from MySQL.", "info")
    except mysql.connector.Error as e:
        flash(f"Cannot delete Museum #{museum_id}: {e}. Ensure no dependent galleries reference it.", "danger")

    return redirect(url_for("list_museums"))


# ==============================================================================
# 3. GALLERIES MODULE (CRUD + Search)
# ==============================================================================
@app.route("/galleries")
def list_galleries():
    """View and search Gallery records joined with Museum names."""
    search_query = request.args.get("q", "").strip()
    galleries = []
    museums = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT museum_id, name FROM Museum ORDER BY name ASC")
        museums = cursor.fetchall()

        base_query = """
            SELECT 
                G.gallery_id,
                G.museum_id,
                G.name,
                G.floor_number,
                M.name AS museum_name
            FROM Gallery G
            LEFT JOIN Museum M ON G.museum_id = M.museum_id
        """

        if search_query:
            query = (
                base_query
                + """
                WHERE G.name LIKE %s OR M.name LIKE %s OR CAST(G.floor_number AS CHAR) LIKE %s
                ORDER BY G.gallery_id ASC
            """
            )
            wildcard = f"%{search_query}%"
            cursor.execute(query, (wildcard, wildcard, wildcard))
        else:
            cursor.execute(base_query + " ORDER BY G.gallery_id ASC")

        galleries = cursor.fetchall()
        cursor.close()
        conn.close()
    except mysql.connector.Error as e:
        flash(f"Error fetching galleries: {e}", "danger")

    return render_template(
        "galleries.html",
        active_page="galleries",
        galleries=galleries,
        museums=museums,
        search_query=search_query,
        edit_gallery=None,
    )


@app.route("/galleries/add", methods=["GET", "POST"])
def add_gallery():
    """Insert a new gallery into MySQL Gallery table."""
    if request.method == "POST":
        try:
            gallery_id = request.form.get("gallery_id", "").strip()
            museum_id = request.form.get("museum_id", "").strip() or None
            name = request.form.get("name", "").strip()
            floor_number = request.form.get("floor_number", "").strip() or None

            if not gallery_id or not name:
                flash("Gallery ID and Name are required.", "warning")
                return redirect(url_for("list_galleries"))

            gallery_id = int(gallery_id)
            if museum_id is not None:
                museum_id = int(museum_id)
            if floor_number is not None:
                floor_number = int(floor_number)

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("SELECT gallery_id FROM Gallery WHERE gallery_id = %s", (gallery_id,))
            if cursor.fetchone():
                flash(f"Gallery with ID #{gallery_id} already exists.", "warning")
                cursor.close()
                conn.close()
                return redirect(url_for("list_galleries"))

            cursor.execute(
                "INSERT INTO Gallery (gallery_id, museum_id, name, floor_number) VALUES (%s, %s, %s, %s)",
                (gallery_id, museum_id, name, floor_number),
            )
            conn.commit()
            cursor.close()
            conn.close()

            flash(f"Gallery '{name}' (ID #{gallery_id}) added successfully to MySQL!", "success")
        except ValueError:
            flash("Gallery ID and Floor Number must be valid integers.", "danger")
        except mysql.connector.Error as e:
            flash(f"MySQL Error inserting gallery: {e}", "danger")

        return redirect(url_for("list_galleries"))

    return redirect(url_for("list_galleries"))


@app.route("/galleries/edit/<int:gallery_id>", methods=["GET", "POST"])
def edit_gallery(gallery_id):
    """View and update an existing gallery in the MySQL Gallery table."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        try:
            museum_id = request.form.get("museum_id", "").strip() or None
            name = request.form.get("name", "").strip()
            floor_number = request.form.get("floor_number", "").strip() or None

            if not name:
                flash("Gallery Name is required.", "warning")
                return redirect(url_for("edit_gallery", gallery_id=gallery_id))

            if museum_id is not None:
                museum_id = int(museum_id)
            if floor_number is not None:
                floor_number = int(floor_number)

            cursor.execute(
                "UPDATE Gallery SET museum_id = %s, name = %s, floor_number = %s WHERE gallery_id = %s",
                (museum_id, name, floor_number, gallery_id),
            )
            conn.commit()
            cursor.close()
            conn.close()

            flash(f"Gallery #{gallery_id} updated successfully in MySQL!", "success")
            return redirect(url_for("list_galleries"))
        except ValueError:
            flash("Floor Number must be an integer.", "danger")
        except mysql.connector.Error as e:
            flash(f"MySQL Error updating gallery #{gallery_id}: {e}", "danger")
            cursor.close()
            conn.close()
            return redirect(url_for("list_galleries"))

    cursor.execute("SELECT * FROM Gallery WHERE gallery_id = %s", (gallery_id,))
    target = cursor.fetchone()

    cursor.execute("SELECT museum_id, name FROM Museum ORDER BY name ASC")
    museums = cursor.fetchall()

    cursor.execute("""
        SELECT G.gallery_id, G.museum_id, G.name, G.floor_number, M.name AS museum_name
        FROM Gallery G LEFT JOIN Museum M ON G.museum_id = M.museum_id
        ORDER BY G.gallery_id ASC
    """)
    galleries = cursor.fetchall()

    cursor.close()
    conn.close()

    if not target:
        flash(f"Gallery #{gallery_id} not found.", "warning")
        return redirect(url_for("list_galleries"))

    return render_template(
        "galleries.html",
        active_page="galleries",
        galleries=galleries,
        museums=museums,
        search_query="",
        edit_gallery=target,
    )


@app.route("/galleries/delete/<int:gallery_id>", methods=["POST"])
def delete_gallery(gallery_id):
    """Delete a gallery from MySQL Gallery table."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("DELETE FROM Gallery WHERE gallery_id = %s", (gallery_id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash(f"Gallery #{gallery_id} deleted successfully from MySQL.", "info")
    except mysql.connector.Error as e:
        flash(f"Cannot delete Gallery #{gallery_id}: {e}. Ensure no artifacts reference this gallery.", "danger")

    return redirect(url_for("list_galleries"))


# ==============================================================================
# 4. CURATORS MODULE (CRUD + Search)
# ==============================================================================
@app.route("/curators")
def list_curators():
    """List and search Curator records from the MySQL Curator table."""
    search_query = request.args.get("q", "").strip()
    curators = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if search_query:
            query = """
                SELECT * FROM Curator 
                WHERE name LIKE %s OR qualification LIKE %s OR phone_number LIKE %s
                ORDER BY curator_id ASC
            """
            wildcard = f"%{search_query}%"
            cursor.execute(query, (wildcard, wildcard, wildcard))
        else:
            cursor.execute("SELECT * FROM Curator ORDER BY curator_id ASC")

        curators = cursor.fetchall()
        cursor.close()
        conn.close()
    except mysql.connector.Error as e:
        flash(f"Error fetching curators: {e}", "danger")

    return render_template(
        "curators.html",
        active_page="curators",
        curators=curators,
        search_query=search_query,
        edit_curator=None,
    )


@app.route("/curators/add", methods=["GET", "POST"])
def add_curator():
    """Insert a new curator into MySQL Curator table."""
    if request.method == "POST":
        try:
            curator_id = request.form.get("curator_id", "").strip()
            name = request.form.get("name", "").strip()
            qualification = request.form.get("qualification", "").strip() or None
            phone_number = request.form.get("phone_number", "").strip() or None

            if not curator_id or not name:
                flash("Curator ID and Name are required.", "warning")
                return redirect(url_for("list_curators"))

            curator_id = int(curator_id)

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("SELECT curator_id FROM Curator WHERE curator_id = %s", (curator_id,))
            if cursor.fetchone():
                flash(f"Curator with ID #{curator_id} already exists.", "warning")
                cursor.close()
                conn.close()
                return redirect(url_for("list_curators"))

            cursor.execute(
                "INSERT INTO Curator (curator_id, name, qualification, phone_number) VALUES (%s, %s, %s, %s)",
                (curator_id, name, qualification, phone_number),
            )
            conn.commit()
            cursor.close()
            conn.close()

            flash(f"Curator '{name}' (ID #{curator_id}) registered successfully in MySQL!", "success")
        except ValueError:
            flash("Curator ID must be an integer.", "danger")
        except mysql.connector.Error as e:
            flash(f"MySQL Error adding curator: {e}", "danger")

        return redirect(url_for("list_curators"))

    return redirect(url_for("list_curators"))


@app.route("/curators/edit/<int:curator_id>", methods=["GET", "POST"])
def edit_curator(curator_id):
    """View and update a curator's details in the MySQL Curator table."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            qualification = request.form.get("qualification", "").strip() or None
            phone_number = request.form.get("phone_number", "").strip() or None

            if not name:
                flash("Curator Name is required.", "warning")
                return redirect(url_for("edit_curator", curator_id=curator_id))

            cursor.execute(
                "UPDATE Curator SET name = %s, qualification = %s, phone_number = %s WHERE curator_id = %s",
                (name, qualification, phone_number, curator_id),
            )
            conn.commit()
            cursor.close()
            conn.close()

            flash(f"Curator #{curator_id} updated successfully in MySQL!", "success")
            return redirect(url_for("list_curators"))
        except mysql.connector.Error as e:
            flash(f"MySQL Error updating curator #{curator_id}: {e}", "danger")
            cursor.close()
            conn.close()
            return redirect(url_for("list_curators"))

    cursor.execute("SELECT * FROM Curator WHERE curator_id = %s", (curator_id,))
    target = cursor.fetchone()

    cursor.execute("SELECT * FROM Curator ORDER BY curator_id ASC")
    curators = cursor.fetchall()

    cursor.close()
    conn.close()

    if not target:
        flash(f"Curator #{curator_id} not found.", "warning")
        return redirect(url_for("list_curators"))

    return render_template(
        "curators.html",
        active_page="curators",
        curators=curators,
        search_query="",
        edit_curator=target,
    )


@app.route("/curators/delete/<int:curator_id>", methods=["POST"])
def delete_curator(curator_id):
    """Delete a curator record from MySQL Curator table."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("DELETE FROM Curator WHERE curator_id = %s", (curator_id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash(f"Curator #{curator_id} deleted successfully from MySQL.", "info")
    except mysql.connector.Error as e:
        flash(f"Cannot delete Curator #{curator_id}: {e}. Ensure no artifacts reference this curator.", "danger")

    return redirect(url_for("list_curators"))


# ==============================================================================
# 5. DONORS MODULE (CRUD + Search)
# ==============================================================================
@app.route("/donors")
def list_donors():
    """List and search Donor records in the MySQL Donor table."""
    search_query = request.args.get("q", "").strip()
    donors = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if search_query:
            query = """
                SELECT * FROM Donor 
                WHERE name LIKE %s OR address LIKE %s OR contact LIKE %s
                ORDER BY donor_id ASC
            """
            wildcard = f"%{search_query}%"
            cursor.execute(query, (wildcard, wildcard, wildcard))
        else:
            cursor.execute("SELECT * FROM Donor ORDER BY donor_id ASC")

        donors = cursor.fetchall()
        cursor.close()
        conn.close()
    except mysql.connector.Error as e:
        flash(f"Error fetching donors: {e}", "danger")

    return render_template(
        "donors.html",
        active_page="donors",
        donors=donors,
        search_query=search_query,
        edit_donor=None,
    )


@app.route("/donors/add", methods=["GET", "POST"])
def add_donor():
    """Insert a new donor into MySQL Donor table."""
    if request.method == "POST":
        try:
            donor_id = request.form.get("donor_id", "").strip()
            name = request.form.get("name", "").strip()
            address = request.form.get("address", "").strip() or None
            contact = request.form.get("contact", "").strip() or None

            if not donor_id or not name:
                flash("Donor ID and Name are required.", "warning")
                return redirect(url_for("list_donors"))

            donor_id = int(donor_id)

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("SELECT donor_id FROM Donor WHERE donor_id = %s", (donor_id,))
            if cursor.fetchone():
                flash(f"Donor with ID #{donor_id} already exists.", "warning")
                cursor.close()
                conn.close()
                return redirect(url_for("list_donors"))

            cursor.execute(
                "INSERT INTO Donor (donor_id, name, address, contact) VALUES (%s, %s, %s, %s)",
                (donor_id, name, address, contact),
            )
            conn.commit()
            cursor.close()
            conn.close()

            flash(f"Donor '{name}' (ID #{donor_id}) successfully registered in MySQL!", "success")
        except ValueError:
            flash("Donor ID must be an integer.", "danger")
        except mysql.connector.Error as e:
            flash(f"MySQL Error inserting donor: {e}", "danger")

        return redirect(url_for("list_donors"))

    return redirect(url_for("list_donors"))


@app.route("/donors/edit/<int:donor_id>", methods=["GET", "POST"])
def edit_donor(donor_id):
    """View and update donor in MySQL Donor table."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            address = request.form.get("address", "").strip() or None
            contact = request.form.get("contact", "").strip() or None

            if not name:
                flash("Donor Name is required.", "warning")
                return redirect(url_for("edit_donor", donor_id=donor_id))

            cursor.execute(
                "UPDATE Donor SET name = %s, address = %s, contact = %s WHERE donor_id = %s",
                (name, address, contact, donor_id),
            )
            conn.commit()
            cursor.close()
            conn.close()

            flash(f"Donor #{donor_id} updated successfully in MySQL!", "success")
            return redirect(url_for("list_donors"))
        except mysql.connector.Error as e:
            flash(f"MySQL Error updating donor #{donor_id}: {e}", "danger")
            cursor.close()
            conn.close()
            return redirect(url_for("list_donors"))

    cursor.execute("SELECT * FROM Donor WHERE donor_id = %s", (donor_id,))
    target = cursor.fetchone()

    cursor.execute("SELECT * FROM Donor ORDER BY donor_id ASC")
    donors = cursor.fetchall()

    cursor.close()
    conn.close()

    if not target:
        flash(f"Donor #{donor_id} not found.", "warning")
        return redirect(url_for("list_donors"))

    return render_template(
        "donors.html",
        active_page="donors",
        donors=donors,
        search_query="",
        edit_donor=target,
    )


@app.route("/donors/delete/<int:donor_id>", methods=["POST"])
def delete_donor(donor_id):
    """Delete donor from MySQL Donor table."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("DELETE FROM Donor WHERE donor_id = %s", (donor_id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash(f"Donor #{donor_id} deleted successfully from MySQL.", "info")
    except mysql.connector.Error as e:
        flash(f"Cannot delete Donor #{donor_id}: {e}. Ensure no artifacts reference this donor.", "danger")

    return redirect(url_for("list_donors"))


# ==============================================================================
# 6. EXHIBITIONS MODULE (CRUD + Search)
# ==============================================================================
@app.route("/exhibitions")
def list_exhibitions():
    """List and search Exhibition records in the MySQL Exhibition table."""
    search_query = request.args.get("q", "").strip()
    exhibitions = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if search_query:
            query = """
                SELECT * FROM Exhibition 
                WHERE title LIKE %s OR CAST(start_date AS CHAR) LIKE %s OR CAST(end_date AS CHAR) LIKE %s
                ORDER BY exhibition_id ASC
            """
            wildcard = f"%{search_query}%"
            cursor.execute(query, (wildcard, wildcard, wildcard))
        else:
            cursor.execute("SELECT * FROM Exhibition ORDER BY exhibition_id ASC")

        exhibitions = cursor.fetchall()
        cursor.close()
        conn.close()
    except mysql.connector.Error as e:
        flash(f"Error fetching exhibitions: {e}", "danger")

    return render_template(
        "exhibitions.html",
        active_page="exhibitions",
        exhibitions=exhibitions,
        search_query=search_query,
        edit_exhibition=None,
    )


@app.route("/exhibitions/add", methods=["GET", "POST"])
def add_exhibition():
    """Insert a new exhibition into MySQL Exhibition table."""
    if request.method == "POST":
        try:
            exhibition_id = request.form.get("exhibition_id", "").strip()
            title = request.form.get("title", "").strip()
            start_date = request.form.get("start_date", "").strip() or None
            end_date = request.form.get("end_date", "").strip() or None

            if not exhibition_id or not title:
                flash("Exhibition ID and Title are required.", "warning")
                return redirect(url_for("list_exhibitions"))

            exhibition_id = int(exhibition_id)

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("SELECT exhibition_id FROM Exhibition WHERE exhibition_id = %s", (exhibition_id,))
            if cursor.fetchone():
                flash(f"Exhibition with ID #{exhibition_id} already exists.", "warning")
                cursor.close()
                conn.close()
                return redirect(url_for("list_exhibitions"))

            cursor.execute(
                "INSERT INTO Exhibition (exhibition_id, title, start_date, end_date) VALUES (%s, %s, %s, %s)",
                (exhibition_id, title, start_date, end_date),
            )
            conn.commit()
            cursor.close()
            conn.close()

            flash(f"Exhibition '{title}' (ID #{exhibition_id}) scheduled successfully in MySQL!", "success")
        except ValueError:
            flash("Exhibition ID must be an integer.", "danger")
        except mysql.connector.Error as e:
            flash(f"MySQL Error inserting exhibition: {e}", "danger")

        return redirect(url_for("list_exhibitions"))

    return redirect(url_for("list_exhibitions"))


@app.route("/exhibitions/edit/<int:exhibition_id>", methods=["GET", "POST"])
def edit_exhibition(exhibition_id):
    """View and update exhibition in MySQL Exhibition table."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        try:
            title = request.form.get("title", "").strip()
            start_date = request.form.get("start_date", "").strip() or None
            end_date = request.form.get("end_date", "").strip() or None

            if not title:
                flash("Exhibition Title is required.", "warning")
                return redirect(url_for("edit_exhibition", exhibition_id=exhibition_id))

            cursor.execute(
                "UPDATE Exhibition SET title = %s, start_date = %s, end_date = %s WHERE exhibition_id = %s",
                (title, start_date, end_date, exhibition_id),
            )
            conn.commit()
            cursor.close()
            conn.close()

            flash(f"Exhibition #{exhibition_id} updated successfully in MySQL!", "success")
            return redirect(url_for("list_exhibitions"))
        except mysql.connector.Error as e:
            flash(f"MySQL Error updating exhibition #{exhibition_id}: {e}", "danger")
            cursor.close()
            conn.close()
            return redirect(url_for("list_exhibitions"))

    cursor.execute("SELECT * FROM Exhibition WHERE exhibition_id = %s", (exhibition_id,))
    target = cursor.fetchone()

    cursor.execute("SELECT * FROM Exhibition ORDER BY exhibition_id ASC")
    exhibitions = cursor.fetchall()

    cursor.close()
    conn.close()

    if not target:
        flash(f"Exhibition #{exhibition_id} not found.", "warning")
        return redirect(url_for("list_exhibitions"))

    return render_template(
        "exhibitions.html",
        active_page="exhibitions",
        exhibitions=exhibitions,
        search_query="",
        edit_exhibition=target,
    )


@app.route("/exhibitions/delete/<int:exhibition_id>", methods=["POST"])
def delete_exhibition(exhibition_id):
    """Delete exhibition from MySQL Exhibition table."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("DELETE FROM Exhibition WHERE exhibition_id = %s", (exhibition_id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash(f"Exhibition #{exhibition_id} deleted successfully from MySQL.", "info")
    except mysql.connector.Error as e:
        flash(f"Cannot delete Exhibition #{exhibition_id}: {e}. Ensure no artifacts reference this exhibition.", "danger")

    return redirect(url_for("list_exhibitions"))


# ==============================================================================
# 7. RESTORATION DEPARTMENT MODULE (CRUD + Search)
# ==============================================================================
@app.route("/restoration")
def list_restorations():
    """List and search Restoration Department records in MySQL Restoration_Department table."""
    search_query = request.args.get("q", "").strip()
    restorations = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if search_query:
            query = """
                SELECT * FROM Restoration_Department 
                WHERE description_for_restoration LIKE %s 
                   OR CAST(date_catalog AS CHAR) LIKE %s 
                   OR CAST(maintenance_cost AS CHAR) LIKE %s
                ORDER BY restoration_id ASC
            """
            wildcard = f"%{search_query}%"
            cursor.execute(query, (wildcard, wildcard, wildcard))
        else:
            cursor.execute("SELECT * FROM Restoration_Department ORDER BY restoration_id ASC")

        restorations = cursor.fetchall()
        cursor.close()
        conn.close()
    except mysql.connector.Error as e:
        flash(f"Error fetching restoration logs: {e}", "danger")

    return render_template(
        "restoration.html",
        active_page="restorations",
        restorations=restorations,
        search_query=search_query,
        edit_restoration=None,
    )


@app.route("/restoration/add", methods=["GET", "POST"])
def add_restoration():
    """Insert a new restoration record into MySQL Restoration_Department table."""
    if request.method == "POST":
        try:
            restoration_id = request.form.get("restoration_id", "").strip()
            date_catalog = request.form.get("date_catalog", "").strip() or None
            maintenance_cost = request.form.get("maintenance_cost", "").strip() or None
            description_for_restoration = request.form.get("description_for_restoration", "").strip() or None

            if not restoration_id:
                flash("Restoration ID is required.", "warning")
                return redirect(url_for("list_restorations"))

            restoration_id = int(restoration_id)
            if maintenance_cost is not None:
                maintenance_cost = float(maintenance_cost)

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute(
                "SELECT restoration_id FROM Restoration_Department WHERE restoration_id = %s",
                (restoration_id,),
            )
            if cursor.fetchone():
                flash(f"Restoration record with ID #{restoration_id} already exists.", "warning")
                cursor.close()
                conn.close()
                return redirect(url_for("list_restorations"))

            cursor.execute(
                """
                INSERT INTO Restoration_Department 
                (restoration_id, date_catalog, maintenance_cost, description_for_restoration) 
                VALUES (%s, %s, %s, %s)
                """,
                (restoration_id, date_catalog, maintenance_cost, description_for_restoration),
            )
            conn.commit()
            cursor.close()
            conn.close()

            flash(f"Restoration log #{restoration_id} created successfully in MySQL!", "success")
        except ValueError:
            flash("Restoration ID and Maintenance Cost must be valid numbers.", "danger")
        except mysql.connector.Error as e:
            flash(f"MySQL Error inserting restoration log: {e}", "danger")

        return redirect(url_for("list_restorations"))

    return redirect(url_for("list_restorations"))


@app.route("/restoration/edit/<int:restoration_id>", methods=["GET", "POST"])
def edit_restoration(restoration_id):
    """View and update restoration record in MySQL Restoration_Department table."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        try:
            date_catalog = request.form.get("date_catalog", "").strip() or None
            maintenance_cost = request.form.get("maintenance_cost", "").strip() or None
            description_for_restoration = request.form.get("description_for_restoration", "").strip() or None

            if maintenance_cost is not None:
                maintenance_cost = float(maintenance_cost)

            cursor.execute(
                """
                UPDATE Restoration_Department 
                SET date_catalog = %s, maintenance_cost = %s, description_for_restoration = %s 
                WHERE restoration_id = %s
                """,
                (date_catalog, maintenance_cost, description_for_restoration, restoration_id),
            )
            conn.commit()
            cursor.close()
            conn.close()

            flash(f"Restoration log #{restoration_id} updated successfully in MySQL!", "success")
            return redirect(url_for("list_restorations"))
        except ValueError:
            flash("Maintenance Cost must be a valid number.", "danger")
        except mysql.connector.Error as e:
            flash(f"MySQL Error updating restoration log #{restoration_id}: {e}", "danger")
            cursor.close()
            conn.close()
            return redirect(url_for("list_restorations"))

    cursor.execute("SELECT * FROM Restoration_Department WHERE restoration_id = %s", (restoration_id,))
    target = cursor.fetchone()

    cursor.execute("SELECT * FROM Restoration_Department ORDER BY restoration_id ASC")
    restorations = cursor.fetchall()

    cursor.close()
    conn.close()

    if not target:
        flash(f"Restoration log #{restoration_id} not found.", "warning")
        return redirect(url_for("list_restorations"))

    return render_template(
        "restoration.html",
        active_page="restorations",
        restorations=restorations,
        search_query="",
        edit_restoration=target,
    )


@app.route("/restoration/delete/<int:restoration_id>", methods=["POST"])
def delete_restoration(restoration_id):
    """Delete restoration record from MySQL Restoration_Department table."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("DELETE FROM Restoration_Department WHERE restoration_id = %s", (restoration_id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash(f"Restoration log #{restoration_id} deleted successfully from MySQL.", "info")
    except mysql.connector.Error as e:
        flash(f"Cannot delete Restoration log #{restoration_id}: {e}. Ensure no artifacts reference this record.", "danger")

    return redirect(url_for("list_restorations"))


# ==============================================================================
# APPLICATION ENTRYPOINT
# ==============================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Museum Management System on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
