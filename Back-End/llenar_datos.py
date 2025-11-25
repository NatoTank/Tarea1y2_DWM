# llenar_datos.py
from main import SessionLocal, ProductoDB, Base, engine

# 1. Crear tablas si no existen
Base.metadata.create_all(bind=engine)

# 2. Lista de productos (Igual a la que tenías en tu Frontend)
productos_iniciales = [
    {"nombre": "Chocolate Avenida", "precio": 5000, "tipo": "con leche", "stock": 20},
    {"nombre": "Chocolate con Leche", "precio": 4000, "tipo": "con leche", "stock": 15},
    {"nombre": "Chocolate Blanco", "precio": 6000, "tipo": "blanco", "stock": 10},
    {"nombre": "Chocolate con Almendras", "precio": 7000, "tipo": "con leche", "stock": 12},
    {"nombre": "Bombones Chocolate Negro", "precio": 8000, "tipo": "Bombones", "stock": 25},
    {"nombre": "Bombones Chocolate Blanco", "precio": 5000, "tipo": "Bombones", "stock": 0}, # Agotado para probar
    {"nombre": "Alfajores", "precio": 5500, "tipo": "Alfajores", "stock": 30},
    {"nombre": "Macaroons", "precio": 7500, "tipo": "Macaroons", "stock": 8},
]

# 3. Insertar en la base de datos
db = SessionLocal()

try:
    print("--- Insertando productos ---")
    for item in productos_iniciales:
        # Verificar si ya existe para no duplicar
        existe = db.query(ProductoDB).filter(ProductoDB.nombre == item["nombre"]).first()
        if not existe:
            nuevo_producto = ProductoDB(
                nombre=item["nombre"],
                precio=item["precio"],
                tipo=item["tipo"],
                stock=item["stock"],
                activo=True,
                descripcion="Delicioso producto artesanal Chocomanía"
            )
            db.add(nuevo_producto)
            print(f"Agregado: {item['nombre']}")
        else:
            print(f"Ya existe: {item['nombre']}")
    
    db.commit()
    print("--- ¡Carga completada con éxito! ---")

except Exception as e:
    print(f"Error: {e}")
    db.rollback()
finally:
    db.close()