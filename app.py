from datetime import date, datetime, timedelta
from functools import wraps
import os
import sqlite3

from flask import (
    Flask, abort, flash, g, redirect,
    render_template, request, session, url_for
)
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "data.sqlite3")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "dev-secret-change-before-deploy"
)
app.config["DATABASE"] = DB_PATH


def db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin', 'merchant')),
        shop_name TEXT NOT NULL DEFAULT '',
        address TEXT NOT NULL DEFAULT '',
        tax_code TEXT NOT NULL DEFAULT '',
        business TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        receipt_no TEXT NOT NULL,
        customer TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        total INTEGER NOT NULL CHECK(total >= 0)
    );

    CREATE TABLE IF NOT EXISTS sale_items (
        id INTEGER PRIMARY KEY,
        sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        quantity INTEGER NOT NULL CHECK(quantity > 0),
        unit_price INTEGER NOT NULL CHECK(unit_price >= 0),
        line_total INTEGER NOT NULL CHECK(line_total >= 0)
    );

    CREATE INDEX IF NOT EXISTS idx_sales_user_date
    ON sales(user_id, created_at);
    """)

    admin_exists = conn.execute(
        "SELECT 1 FROM users WHERE username = 'admin'"
    ).fetchone()

    if not admin_exists:
        conn.execute(
            """
            INSERT INTO users(username, password, role, shop_name)
            VALUES (?, ?, ?, ?)
            """,
            (
                "admin",
                generate_password_hash("admin123"),
                "admin",
                "Quản trị hệ thống",
            ),
        )

    shop_exists = conn.execute(
        "SELECT 1 FROM users WHERE username = 'cuahang'"
    ).fetchone()

    if not shop_exists:
        conn.execute(
            """
            INSERT INTO users(username, password, role, shop_name, business)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "cuahang",
                generate_password_hash("shop123"),
                "merchant",
                "Cửa hàng mẫu",
                "Bán lẻ",
            ),
        )

    conn.commit()
    conn.close()


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None

    return db().execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
@app.context_processor
def inject_current_user():
    return {"current_user": current_user}


def login_required(role=None):
    def decorator(view_function):
        @wraps(view_function)
        def wrapped(*args, **kwargs):
            user = current_user()

            if not user:
                return redirect(url_for("login", next=request.path))

            if role and user["role"] != role:
                abort(403)

            return view_function(*args, **kwargs)

        return wrapped

    return decorator


def period_bounds(period, value):
    try:
        if period == "day":
            selected_date = date.fromisoformat(value)
            start = selected_date.isoformat()
            end = (selected_date + timedelta(days=1)).isoformat()

        elif period == "month":
            selected_month = datetime.strptime(value, "%Y-%m")
            start = selected_month.strftime("%Y-%m-01")
            next_month = (
                selected_month.replace(day=28) + timedelta(days=4)
            ).replace(day=1)
            end = next_month.strftime("%Y-%m-%d")

        else:
            year = int(value)
            start = f"{year:04d}-01-01"
            end = f"{year + 1:04d}-01-01"

        return start, end

    except (ValueError, TypeError):
        today = date.today()
        return today.isoformat(), (today + timedelta(days=1)).isoformat()


@app.route("/")
def home():
    user = current_user()

    if not user:
        return redirect(url_for("login"))

    if user["role"] == "admin":
        return redirect(url_for("admin_dashboard"))

    return redirect(url_for("shop_dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = db().execute(
            "SELECT * FROM users WHERE username = ?",
            (username,),
        ).fetchone()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]

            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))

            return redirect(url_for("shop_dashboard"))

        flash("Tên đăng nhập hoặc mật khẩu chưa đúng.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/admin")
@login_required("admin")
def admin_dashboard():
    period = request.args.get("period", "month")
    value = request.args.get("value", date.today().strftime("%Y-%m"))
    start, end = period_bounds(period, value)

    totals = db().execute(
        """
        SELECT
            COUNT(*) AS orders,
            COALESCE(SUM(total), 0) AS revenue,
            COUNT(DISTINCT user_id) AS shops
        FROM sales
        WHERE created_at >= ? AND created_at < ?
        """,
        (start, end),
    ).fetchone()

    shops = db().execute(
        """
        SELECT
            u.*,
            COUNT(s.id) AS order_count,
            COALESCE(SUM(s.total), 0) AS revenue
        FROM users u
        LEFT JOIN sales s
            ON s.user_id = u.id
            AND s.created_at >= ?
            AND s.created_at < ?
        WHERE u.role = 'merchant'
        GROUP BY u.id
        ORDER BY revenue DESC
        """,
        (start, end),
    ).fetchall()

    recent = db().execute(
        """
        SELECT s.*, u.shop_name
        FROM sales s
        JOIN users u ON u.id = s.user_id
        WHERE s.created_at >= ? AND s.created_at < ?
        ORDER BY s.id DESC
        LIMIT 12
        """,
        (start, end),
    ).fetchall()

    return render_template(
        "admin.html",
        totals=totals,
        shops=shops,
        recent=recent,
        period=period,
        value=value,
    )


@app.route("/admin/shops", methods=["GET", "POST"])
@login_required("admin")
def admin_shops():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        shop_name = request.form.get("shop_name", "").strip()

        if not username or len(password) < 6 or not shop_name:
            flash(
                "Nhập tên cửa hàng, tên đăng nhập và mật khẩu "
                "tối thiểu 6 ký tự.",
                "danger",
            )
            return redirect(url_for("admin_shops"))

        try:
            db().execute(
                """
                INSERT INTO users(
                    username, password, role, shop_name,
                    address, tax_code, business
                )
                VALUES (?, ?, 'merchant', ?, ?, ?, ?)
                """,
                (
                    username,
                    generate_password_hash(password),
                    shop_name,
                    request.form.get("address", "").strip(),
                    request.form.get("tax_code", "").strip(),
                    request.form.get("business", "").strip(),
                ),
            )
            db().commit()
            flash("Đã tạo tài khoản cửa hàng.", "success")

        except sqlite3.IntegrityError:
            flash("Tên đăng nhập đã được sử dụng.", "danger")

        return redirect(url_for("admin_shops"))

    shops = db().execute(
        """
        SELECT
            u.*,
            COUNT(s.id) AS orders,
            COALESCE(SUM(s.total), 0) AS revenue
        FROM users u
        LEFT JOIN sales s ON s.user_id = u.id
        WHERE u.role = 'merchant'
        GROUP BY u.id
        ORDER BY u.id DESC
        """
    ).fetchall()

    return render_template("shops.html", shops=shops)


@app.route("/shop")
@login_required("merchant")
def shop_dashboard():
    user = current_user()
    period = request.args.get("period", "day")
    value = request.args.get("value", date.today().isoformat())
    start, end = period_bounds(period, value)

    totals = db().execute(
        """
        SELECT COUNT(*) AS orders, COALESCE(SUM(total), 0) AS revenue
        FROM sales
        WHERE user_id = ? AND created_at >= ? AND created_at < ?
        """,
        (user["id"], start, end),
    ).fetchone()

    recent = db().execute(
        """
        SELECT * FROM sales
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 10
        """,
        (user["id"],),
    ).fetchall()

    return render_template(
        "shop.html",
        user=user,
        totals=totals,
        recent=recent,
        period=period,
        value=value,
    )


@app.route("/shop/profile", methods=["GET", "POST"])
@login_required("merchant")
def shop_profile():
    user = current_user()

    if request.method == "POST":
        db().execute(
            """
            UPDATE users
            SET shop_name = ?, address = ?, tax_code = ?, business = ?
            WHERE id = ?
            """,
            (
                request.form.get("shop_name", "").strip(),
                request.form.get("address", "").strip(),
                request.form.get("tax_code", "").strip(),
                request.form.get("business", "").strip(),
                user["id"],
            ),
        )
        db().commit()
        flash("Đã lưu thông tin cửa hàng.", "success")
        return redirect(url_for("shop_profile"))

    return render_template("profile.html", user=user)


@app.route("/shop/sales/new", methods=["GET", "POST"])
@login_required("merchant")
def new_sale():
    user = current_user()

    if request.method == "POST":
        names = request.form.getlist("item_name[]")
        quantities = request.form.getlist("quantity[]")
        prices = request.form.getlist("unit_price[]")
        items = []

        try:
            for name, quantity, price in zip(names, quantities, prices):
                name = name.strip()
                quantity = int(quantity)
                price = int(price)

                if name and quantity > 0 and price >= 0:
                    items.append((name, quantity, price, quantity * price))

        except (ValueError, TypeError):
            items = []

        if not items:
            flash("Vui lòng nhập ít nhất một mặt hàng hợp lệ.", "danger")
            return render_template("new_sale.html", user=user)

        conn = db()
        cursor = conn.execute(
            """
            INSERT INTO sales(user_id, receipt_no, customer, created_at, total)
            VALUES (?, '', ?, ?, ?)
            """,
            (
                user["id"],
                request.form.get("customer", "").strip(),
                datetime.now().isoformat(timespec="seconds"),
                sum(item[3] for item in items),
            ),
        )

        sale_id = cursor.lastrowid
        receipt_no = f"HD-{datetime.now():%Y%m%d}-{sale_id:04d}"

        conn.execute(
            "UPDATE sales SET receipt_no = ? WHERE id = ?",
            (receipt_no, sale_id),
        )

        conn.executemany(
            """
            INSERT INTO sale_items(
                sale_id, name, quantity, unit_price, line_total
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            [(sale_id, *item) for item in items],
        )

        conn.commit()
        return redirect(url_for("receipt", sale_id=sale_id))

    return render_template("new_sale.html", user=user)


@app.route("/shop/receipt/<int:sale_id>")
@login_required()
def receipt(sale_id):
    user = current_user()

    sale = db().execute(
        """
        SELECT s.*, u.shop_name, u.address, u.tax_code, u.business
        FROM sales s
        JOIN users u ON u.id = s.user_id
        WHERE s.id = ?
        """,
        (sale_id,),
    ).fetchone()

    if not sale:
        abort(404)

    if user["role"] != "admin" and sale["user_id"] != user["id"]:
        abort(404)

    items = db().execute(
        "SELECT * FROM sale_items WHERE sale_id = ?",
        (sale_id,),
    ).fetchall()

    return render_template("receipt.html", sale=sale, items=items)


@app.errorhandler(403)
def forbidden(_error):
    return render_template(
        "message.html",
        title="Không có quyền truy cập",
        message="Tài khoản hiện tại không được phép mở trang này.",
    ), 403


init_db()

if __name__ == "__main__":
    app.run(debug=False)