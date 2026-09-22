import os
import logging
from typing import Optional
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

load_dotenv()

logger = logging.getLogger("uvicorn.info")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in environment variables / .env file.")

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, pool_size=10, max_overflow=20)

async def get_medicine_details(medicine_name: Optional[str] = None) -> list:
    """
    Returns medicines matching medicine_name using PostgreSQL similarity() and ILIKE filtering.
    Returns empty list if no medicine_name is provided.
    """
    if not medicine_name or not isinstance(medicine_name, str) or not medicine_name.strip():
        return []

    import re
    clean_name = medicine_name.strip()
    first_word = clean_name.split()[0] if clean_name else clean_name
    first_3 = clean_name[:3] if len(clean_name) >= 3 else clean_name
    
    brand_base = re.sub(r'\b\d+(?:\.\d+)?(?:mg|g|ml|mcg|kg|l)?\b', '', clean_name, flags=re.IGNORECASE).strip()
    brand_base = re.sub(r'\b(?:mg|g|ml|mcg|kg|l)\b', '', brand_base, flags=re.IGNORECASE).strip()
    if not brand_base:
        brand_base = first_word

    try:
        async with engine.connect() as connection:
            query = text("""
                SELECT 
                    p.product_code,
                    p.product_name,
                    g.generic_name,
                    p.package_type,
                    SUM(b.stock_quantity) AS total_stock, 
                    MIN(b.selling_price) AS min_price 
                FROM product_m p 
                JOIN batch_m b ON p.product_code = b.product_code
                JOIN generic_m g ON p.generic_code = g.generic_code 
                WHERE p.product_name ILIKE :med_like
                   OR p.product_name ILIKE :first_word_like
                   OR p.product_name ILIKE :brand_base_like
                   OR similarity(p.product_name, :med_name) > 0.2
                   OR similarity(p.product_name, :brand_base) > 0.2
                   OR LOWER(LEFT(p.product_name, 3)) = LOWER(:first_3)
                GROUP BY p.product_code, p.product_name, g.generic_name, p.package_type
                ORDER BY 
                   GREATEST(
                       similarity(p.product_name, :med_name),
                       similarity(p.product_name, :brand_base)
                   ) DESC,
                   p.product_name ASC
                LIMIT 50
            """)
            result = await connection.execute(
                query, 
                {
                    "med_name": clean_name, 
                    "brand_base": brand_base,
                    "med_like": f"%{clean_name}%",
                    "first_word_like": f"%{first_word}%",
                    "brand_base_like": f"%{brand_base}%",
                    "first_3": first_3
                }
            )
            results = result.fetchall()
            
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
        logger.error(f"Error in get_all_medicines_details: {e}")
        return []




async def place_bulk_order(data) -> str:
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
        async with engine.connect() as connection:
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
                        result = await connection.execute(stk_query, {"p_code": str(p_code)})
                        row = result.fetchone()

                    # Fallback lookup by medicine_name if p_code was invalid/non-numeric or not found
                    if not row and m_name:
                        stk_query = text("""
                            SELECT p.product_code, p.product_name, p.package_type, SUM(b.stock_quantity) as total_stock
                            FROM product_m p 
                            JOIN batch_m b ON p.product_code = b.product_code
                            WHERE LOWER(p.product_name) = LOWER(:m_name)
                               OR LOWER(p.product_name) LIKE LOWER(:like_m_name)
                            GROUP BY p.product_code, p.product_name, p.package_type
                            ORDER BY 
                               CASE WHEN LOWER(p.product_name) = LOWER(:m_name) THEN 1
                                    ELSE 2 END
                            LIMIT 1
                        """)
                        clean_name = str(m_name).strip()
                        result = await connection.execute(stk_query, {
                            "m_name": clean_name,
                            "like_m_name": f"%{clean_name}%"
                        })
                        row = result.fetchone()

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

        async with engine.begin() as connection:
            # Ensure product_code column exists in order_m table
            try:
                await connection.execute(text("ALTER TABLE order_m ADD COLUMN IF NOT EXISTS product_code VARCHAR(50);"))
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
                        result = await connection.execute(
                            text("""
                                SELECT product_code, product_name 
                                FROM product_m 
                                WHERE LOWER(product_name) = LOWER(:m_name) 
                                   OR LOWER(product_name) LIKE LOWER(:like_m_name)
                                ORDER BY 
                                   CASE WHEN LOWER(product_name) = LOWER(:m_name) THEN 1 
                                        ELSE 2 END
                                LIMIT 1
                            """),
                            {"m_name": clean_m_name, "like_m_name": f"%{clean_m_name}%"}
                        )
                        code_row = result.fetchone()
                        if code_row:
                            p_code = code_row.product_code
                            medicine_name = code_row.product_name

                    await connection.execute(query, {
                        "product_code": str(p_code) if p_code else None,
                        "medicine_name": medicine_name, 
                        "quantity": quantity
                    })
                
        summary = ", ".join([f"{item.get('quantity')} {item.get('medicine_name') or item.get('product_code')}" for item in items_list if isinstance(item, dict)])
        return f"Order confirmed and saved successfully for: {summary}."
    except Exception as e:
        return f"Failed to save order: {e}"


async def search_medicine_fuzzy(terms: list) -> list:
    """
    Trigram Similarity & Prefix Search for 10,000+ items using pg_trgm.
    Returns multiple matching variants capped at 6.
    """
    if not terms:
        return []
    results = []
    seen = set()
    try:
        async with engine.connect() as connection:
            for term in terms:
                clean_term = term.strip()
                contains_term = f"%{clean_term}%"
                query = text("""
                    SELECT 
                        p.product_name,
                        p.package_type,
                        SUM(b.stock_quantity) as total_stock, 
                        MIN(b.selling_price) as min_price
                    FROM product_m p 
                    JOIN batch_m b ON p.product_code = b.product_code
                    WHERE p.product_name ILIKE :contains_term
                       OR similarity(p.product_name, :clean_term) > 0.25
                    GROUP BY p.product_code, p.product_name, p.package_type
                    ORDER BY similarity(p.product_name, :clean_term) DESC, LOWER(p.product_name) ASC
                    LIMIT 6
                """)
                result = await connection.execute(query, {
                    "contains_term": contains_term,
                    "clean_term": clean_term
                })
                rows = result.fetchall()
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
        logger.error(f"Error in search_medicine_fuzzy: {e}")
    return results


async def check_db_connection():
    try:
        async with engine.connect() as connection:
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
            await connection.execute(text("SELECT 1"))
            logger.info("✅ Database connected successfully with pg_trgm!")
            return True
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False


async def get_medicine_stock(medicine_name=None):
    from services.medicine_service import check_medicine_stock
    return await check_medicine_stock(medicine_name)

