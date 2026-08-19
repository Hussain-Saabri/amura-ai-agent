import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in environment variables / .env file.")

engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)

def get_all_medicines_details() -> list:
    """
    Returns a list of all medicines with their product_code, stock, price, and status.
    """
    try:
        with engine.connect() as connection:
            query = text("""
                SELECT 
                    p.product_code,
                    p.product_name,
                    g.generic_name,
                    p.package_type,
                    SUM(b.stock_quantity) as total_stock, 
                    MIN(b.selling_price) as min_price 
                FROM product_m p 
                JOIN batch_m b ON p.product_code = b.product_code
                JOIN generic_m g ON p.generic_code = g.generic_code 
                GROUP BY p.product_code, p.product_name, g.generic_name, p.package_type
            """)
            results = connection.execute(query).fetchall()
            
            available_by_generic = {}
            parsed_results = []
            
            for row in results:
                stock = int(row.total_stock) if row.total_stock else 0
                price = float(row.min_price) if row.min_price else 0
                status = "available" if stock > 0 else "out_of_stock"
                package_type = row.package_type  
                
                if stock > 0:
                    sub_info = f"{row.product_name} [Code: {row.product_code}, Stock: {stock} {package_type}, Price: {price}]"
                    available_by_generic[row.generic_name] = available_by_generic.get(row.generic_name, []) + [sub_info]
                        
                parsed_results.append({
                    "product_code": str(row.product_code),
                    "medicine_name": row.product_name,
                    "generic_name": row.generic_name,
                    "package_type": package_type,
                    "quantity": stock,
                    "price": price,
                    "status": status
                })

            # Second pass: assign substitute if out of stock (limit to max 6)
            medicines = []
            for item in parsed_results:
                if item["status"] == "out_of_stock":
                    sub = available_by_generic.get(item["generic_name"])
                    if sub:
                        item["substitute"] = sub[:6]
                item.pop("generic_name", None)
                medicines.append(item)
                
            return medicines
    except Exception as e:
        return []


def place_bulk_order(data) -> str:
    import json
    import ast
    
    # Extract items from Pydantic object or dict
    if isinstance(data, dict):
        raw_items = data.get("items", data)
    elif hasattr(data, "items") and not callable(getattr(data, "items")):
        raw_items = getattr(data, "items")
    else:
        raw_items = data
        
    # Recursively unwrap stringified JSON, single-quoted python repr strings, or dict wrappers
    while True:
        if isinstance(raw_items, str):
            raw_items_str = raw_items.strip()
            parsed = None
            try:
                parsed = json.loads(raw_items_str)
            except Exception:
                try:
                    parsed = ast.literal_eval(raw_items_str)
                except Exception:
                    pass
            if parsed is not None and parsed != raw_items:
                raw_items = parsed
            else:
                break
        elif isinstance(raw_items, dict) and "items" in raw_items:
            raw_items = raw_items["items"]
        else:
            break
            
    if isinstance(raw_items, str):
        try:
            raw_items = ast.literal_eval(raw_items)
        except Exception:
            pass

    # Ensure items_list is a list of dictionaries
    if isinstance(raw_items, list):
        items_list = raw_items
    elif isinstance(raw_items, dict):
        items_list = [raw_items]
    else:
        items_list = []
        
    if not items_list:
        return "Failed to save order: No order items found."

    # Stock validation pass
    stock_errors = []
    try:
        with engine.connect() as connection:
            for item in items_list:
                if isinstance(item, dict):
                    p_code = item.get("product_code") or item.get("product_id")
                    m_name = item.get("medicine_name") or item.get("product_name")
                    req_qty = int(item.get("quantity", 1))
                    
                    row = None
                    if p_code and str(p_code).isdigit():
                        stk_query = text("""
                            SELECT p.product_code, p.product_name, p.package_type, SUM(b.stock_quantity) as total_stock
                            from product_m p 
                            JOIN batch_m b ON p.product_code = b.product_code
                            WHERE p.product_code = :p_code
                            GROUP BY p.product_code, p.product_name, p.package_type
                        """)
                        row = connection.execute(stk_query, {"p_code": str(p_code)}).fetchone()

                    # Fallback lookup by medicine_name if p_code was invalid/non-numeric or not found
                    if not row and m_name:
                        stk_query = text("""
                            SELECT TOP 1 p.product_code, p.product_name, p.package_type, SUM(b.stock_quantity) as total_stock
                            FROM product_m p 
                            JOIN batch_m b ON p.product_code = b.product_code
                            WHERE LOWER(p.product_name) = LOWER(:m_name)
                               OR LOWER(p.product_name) LIKE LOWER(:like_m_name)
                               OR DIFFERENCE(LOWER(p.product_name), LOWER(:m_name)) >= 3
                            GROUP BY p.product_code, p.product_name, p.package_type
                            ORDER BY 
                               CASE WHEN LOWER(p.product_name) = LOWER(:m_name) THEN 1
                                    WHEN LOWER(p.product_name) LIKE LOWER(:like_m_name) THEN 2
                                    ELSE 3 END,
                               DIFFERENCE(LOWER(p.product_name), LOWER(:m_name)) DESC
                        """)
                        clean_name = str(m_name).strip()
                        row = connection.execute(stk_query, {
                            "m_name": clean_name,
                            "like_m_name": f"%{clean_name}%"
                        }).fetchone()

                    if row:
                        avail = int(row.total_stock) if row.total_stock else 0
                        pkg = row.package_type
                        name_display = row.product_name or m_name or p_code
                        if req_qty > avail:
                            stock_errors.append(f"Requested {req_qty} {pkg} of '{name_display}', but only {avail} {pkg} available in stock.")
                    else:
                        name_display = m_name or p_code
                        stock_errors.append(f"Medicine '{name_display}' not found in inventory.")

        if stock_errors:
            return "Order placement failed due to stock limits: " + " | ".join(stock_errors)

        with engine.begin() as connection:
            # Ensure product_code column exists in order_m table
            try:
                connection.execute(text("""
                    IF NOT EXISTS (
                        SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_NAME = 'order_m' AND COLUMN_NAME = 'product_code'
                    )
                    BEGIN
                        ALTER TABLE order_m ADD product_code VARCHAR(50);
                    END
                """))
            except Exception:
                pass

            query = text("""
                INSERT INTO order_m (product_code, product_name, quantity) 
                VALUES (:product_code, :medicine_name, :quantity)
            """)
            
            # Execute the query for each item
            for item in items_list:
                if isinstance(item, dict):
                    p_code = item.get("product_code") or item.get("product_id")
                    medicine_name = item.get("medicine_name") or item.get("product_name")
                    quantity = item.get("quantity", 1)
                    
                    if not p_code or not str(p_code).isdigit():
                        clean_m_name = str(medicine_name or p_code).strip()
                        code_row = connection.execute(
                            text("""
                                SELECT TOP 1 product_code, product_name 
                                FROM product_m 
                                WHERE LOWER(product_name) = LOWER(:m_name) 
                                   OR LOWER(product_name) LIKE LOWER(:like_m_name)
                                   OR DIFFERENCE(LOWER(product_name), LOWER(:m_name)) >= 3 
                                ORDER BY 
                                   CASE WHEN LOWER(product_name) = LOWER(:m_name) THEN 1 
                                        WHEN LOWER(product_name) LIKE LOWER(:like_m_name) THEN 2 
                                        ELSE 3 END,
                                   DIFFERENCE(LOWER(product_name), LOWER(:m_name)) DESC
                            """),
                            {"m_name": clean_m_name, "like_m_name": f"%{clean_m_name}%"}
                        ).fetchone()
                        if code_row:
                            p_code = code_row.product_code
                            medicine_name = code_row.product_name

                    connection.execute(query, {
                        "product_code": str(p_code) if p_code else None,
                        "medicine_name": medicine_name, 
                        "quantity": quantity
                    })
                
        summary = ", ".join([f"{item.get('quantity')} {item.get('medicine_name') or item.get('product_code')}" for item in items_list if isinstance(item, dict)])
        return f"Order confirmed and saved successfully for: {summary}."
    except Exception as e:
        return f"Failed to save order: {e}"


def search_medicine_fuzzy(terms: list) -> list:
    """
    Trigram Similarity & Prefix Search for 10,000+ items.
    Returns multiple matching variants capped at 6.
    """
    if not terms:
        return []
    results = []
    seen = set()
    try:
        with engine.connect() as connection:
            for term in terms:
                clean_term = term.strip()
                prefix_term = f"{clean_term}%"
                contains_term = f"%{clean_term}%"
                query = text("""
                    SELECT TOP 6 
                        p.product_name,
                        p.package_type,
                        SUM(b.stock_quantity) as total_stock, 
                        MIN(b.selling_price) as min_price,
                        DIFFERENCE(LOWER(p.product_name), LOWER(:term)) as score
                    FROM product_m p 
                    JOIN batch_m b ON p.product_code = b.product_code
                    WHERE LOWER(p.product_name) LIKE LOWER(:prefix_term)
                       OR LOWER(p.product_name) LIKE LOWER(:contains_term)
                       OR DIFFERENCE(LOWER(p.product_name), LOWER(:term)) >= 3
                    GROUP BY p.product_code, p.product_name, p.package_type
                    ORDER BY score DESC, LOWER(p.product_name) ASC
                """)
                rows = connection.execute(query, {
                    "term": clean_term,
                    "prefix_term": prefix_term,
                    "contains_term": contains_term
                }).fetchall()
                for row in rows:
                    if row.product_name not in seen:
                        seen.add(row.product_name)
                        stock = int(row.total_stock) if row.total_stock else 0
                        price = float(row.min_price) if row.min_price else 0
                        results.append({
                            "medicine_name": row.product_name,
                            "package_type": row.package_type,
                            "quantity": stock,
                            "price": price,
                            "status": "available" if stock > 0 else "out_of_stock"
                        })
    except Exception as e:
        print(f"Error in search_medicine_fuzzy: {e}", flush=True)
    return results


def check_db_connection():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            print("✅ Database connected successfully!", flush=True)
            return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}", flush=True)
        return False

def init_stt_alias_table():
    try:
        with engine.begin() as connection:
            connection.execute(text("""
                IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'stt_alias_m')
                BEGIN
                    CREATE TABLE stt_alias_m (
                        id INT IDENTITY(1,1) PRIMARY KEY,
                        stt_mishearing VARCHAR(255) UNIQUE NOT NULL,
                        correct_medicine VARCHAR(255) NOT NULL,
                        created_at DATETIME DEFAULT GETDATE()
                    );
                END
            """))
    except Exception as e:
        print(f"Error initializing stt_alias_m table: {e}", flush=True)

try:
    init_stt_alias_table()
except Exception:
    pass

def get_learned_stt_aliases() -> dict:
    """Fetch all learned STT mishearings mapped to their correct medicine names."""
    aliases = {}
    try:
        with engine.connect() as connection:
            query = text("SELECT stt_mishearing, correct_medicine FROM stt_alias_m")
            rows = connection.execute(query).fetchall()
            for r in rows:
                aliases[r.stt_mishearing.strip().lower()] = r.correct_medicine.strip()
    except Exception as e:
        init_stt_alias_table()
    return aliases

def save_learned_stt_alias(stt_mishearing: str, correct_medicine: str) -> bool:
    """Save or update a learned STT mishearing alias into DB."""
    if not stt_mishearing or not correct_medicine:
        return False
    stt_clean = stt_mishearing.strip().lower()
    correct_clean = correct_medicine.strip()
    if stt_clean == correct_clean.lower():
        return False
    try:
        with engine.begin() as connection:
            query = text("""
                MERGE INTO stt_alias_m WITH (HOLDLOCK) AS target
                USING (SELECT :stt_mishearing AS stt_mishearing, :correct_medicine AS correct_medicine) AS source
                ON (target.stt_mishearing = source.stt_mishearing)
                WHEN MATCHED THEN
                    UPDATE SET target.correct_medicine = source.correct_medicine
                WHEN NOT MATCHED THEN
                    INSERT (stt_mishearing, correct_medicine)
                    VALUES (source.stt_mishearing, source.correct_medicine);
            """)
            connection.execute(query, {
                "stt_mishearing": stt_clean,
                "correct_medicine": correct_clean
            })
            print(f"✅ Dynamic STT Alias Learned & Saved: '{stt_clean}' ➡️ '{correct_clean}'", flush=True)
            return True
    except Exception as e:
        print(f"Error saving STT alias: {e}", flush=True)
def get_medicine_stock(medicine_name=None):
    from services.medicine_service import check_medicine_stock
    return check_medicine_stock(medicine_name)

try:
    check_db_connection()
except Exception:
    pass



