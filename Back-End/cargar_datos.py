import sqlite3

# Conectar a la base de datos
conn = sqlite3.connect("chocomania.db")
cursor = conn.cursor()

print("--- LIMPIANDO BASE DE DATOS ---")
# Borramos los datos de las tablas
try:
    cursor.execute("DELETE FROM productos")
    cursor.execute("DELETE FROM promociones")
    
    # Intentamos reiniciar los contadores de ID (esto fallaba antes)
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='productos'")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='promociones'")
except sqlite3.OperationalError:
    # Si sqlite_sequence no existe, significa que la base es nueva. No pasa nada.
    print("Nota: Base de datos nueva, no fue necesario reiniciar contadores.")

# Datos de Productos (Nombre, Descripción, Precio, Tipo, Stock)
productos = [
    ("Chocolate Avenida", "Chocolate de leche clásico", 5000, "Tabletas", 10),
    ("Chocolate con Leche", "Suave y cremoso", 4000, "con leche", 5),
    ("Chocolate Blanco", "Dulce chocolate blanco", 6000, "Tabletas", 0), 
    ("Chocolate Almendras", "Con almendras tostadas", 7000, "Tabletas", 3),
    ("Bombones Surtidos", "Caja de 12 unidades mixtas", 12990, "Bombones", 15),
    ("Bombones Blanco", "Rellenos de crema de avellana", 5000, "Bombones", 0),
    ("Alfajores", "Rellenos con manjar casero", 5500, "Alfajores", 8),
    ("Macaroons", "Surtido de colores y sabores", 7500, "Macaroons", 2),
    ("Bombones Licor", "Rellenos de licor fino", 15990, "Bombones", 10),
    ("Bombones Especiales", "Edición Limitada", 18990, "Bombones", 6)
]

print("\n--- CARGANDO PRODUCTOS ---")
for prod in productos:
    try:
        cursor.execute("""
            INSERT INTO productos (nombre, descripcion, precio, tipo, stock, activo)
            VALUES (?, ?, ?, ?, ?, 1)
        """, prod)
        print(f"✅ Agregado: {prod[0]}")
    except Exception as e:
        print(f"❌ Error con {prod[0]}: {e}")

print("\n--- CARGANDO PROMOCIONES ---")
try:
    cursor.execute("SELECT id FROM productos WHERE nombre = 'Bombones Surtidos'")
    resultado = cursor.fetchone()
    
    if resultado:
        prod_id = resultado[0]
        cursor.execute("""
            INSERT INTO promociones (producto_id, precio_oferta, fecha_inicio, fecha_termino, activo)
            VALUES (?, 10990, datetime('now'), '2025-12-31 23:59:59', 1)
        """, (prod_id,))
        print(f"✅ Promoción creada para Bombones Surtidos (ID: {prod_id})")
    else:
        print("⚠️ No se encontró el producto para la promoción")

except Exception as e:
    print(f"❌ Error creando promoción: {e}")

conn.commit()
conn.close()
print("\n¡Listo! Base de datos cargada. Ejecuta uvicorn ahora.")