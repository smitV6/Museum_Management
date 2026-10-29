import os
import mysql.connector
from mysql.connector import Error as MySQLError

# Optional support for local .env files (ignored in production if not installed)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class DatabaseConfigError(Exception):
    """Raised when mandatory database environment variables are missing."""
    pass


class DatabaseConnectionError(Exception):
    """Raised when connection to the remote MySQL database fails."""
    pass


class DatabaseQueryError(Exception):
    """Raised when an SQL query fails during execution."""
    pass


def get_db_config():
    """
    Load and validate database credentials from environment variables exclusively.
    Does NOT hardcode localhost or default credentials.
    """
    host = os.environ.get("DB_HOST", "").strip()
    user = os.environ.get("DB_USER", "").strip()
    name = os.environ.get("DB_NAME", "").strip()
    password = os.environ.get("DB_PASSWORD", "").strip()
    port_str = os.environ.get("DB_PORT", "3306").strip()

    # Identify any missing essential configuration
    missing = []
    if not host:
        missing.append("DB_HOST")
    if not user:
        missing.append("DB_USER")
    if not name:
        missing.append("DB_NAME")

    if missing:
        missing_vars = ", ".join(missing)
        raise DatabaseConfigError(
            f"Missing required database environment variable(s): {missing_vars}. "
            f"Please set these in your Vercel Dashboard under Settings > Environment Variables."
        )

    try:
        port = int(port_str)
    except ValueError:
        raise DatabaseConfigError(
            f"Invalid DB_PORT '{port_str}'. DB_PORT must be an integer (default 3306)."
        )

    config = {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": name,
        "connection_timeout": int(os.environ.get("DB_CONNECT_TIMEOUT", 5)),
        "autocommit": False,
    }

    # Cloud MySQL providers (e.g., TiDB Cloud, Aiven, PlanetScale, AWS RDS)
    # often require SSL. Support DB_SSL_CA or DB_SSL_DISABLED if specified.
    ssl_ca = os.environ.get("DB_SSL_CA", "").strip()
    ssl_disabled = os.environ.get("DB_SSL_DISABLED", "").strip().lower() in ("true", "1", "yes")

    if ssl_ca and os.path.exists(ssl_ca):
        config["ssl_ca"] = ssl_ca
    elif ssl_disabled:
        config["ssl_disabled"] = True

    return config


def get_db_connection():
    """
    Establish and return a live connection to the remote cloud-hosted MySQL database.
    Catches errors with clear diagnostics.
    """
    config = get_db_config()
    try:
        connection = mysql.connector.connect(**config)
        return connection
    except mysql.connector.Error as err:
        host = config.get("host")
        port = config.get("port")
        user = config.get("user")
        db = config.get("database")
        raise DatabaseConnectionError(
            f"Failed to connect to MySQL database at '{host}:{port}' (User: '{user}', Database: '{db}'): {err}"
        ) from err


def check_db_health():
    """
    Performs a lightweight health check query (SELECT 1).
    Returns (is_healthy, info_dict).
    """
    try:
        config = get_db_config()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()
        return True, {
            "status": "healthy",
            "host": config["host"],
            "port": config["port"],
            "database": config["database"],
            "user": config["user"],
            "error": None,
        }
    except Exception as err:
        host_info = os.environ.get("DB_HOST", "NOT_SET")
        port_info = os.environ.get("DB_PORT", "NOT_SET")
        return False, {
            "status": "unhealthy",
            "host": host_info,
            "port": port_info,
            "database": os.environ.get("DB_NAME", "NOT_SET"),
            "user": os.environ.get("DB_USER", "NOT_SET"),
            "error": str(err),
        }
