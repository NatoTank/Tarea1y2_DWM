# llenar_datos.py
from main import SessionLocal, ProductoDB, PromocionDB, Base, engine
from datetime import datetime, timedelta, timezone

# 1. Crear tablas si no existen
Base.metadata.create_all(bind=engine)

# ✅ 2. Lista de productos ACTUALIZADA (con stock de 100 y tipos correctos)
productos_iniciales = [
    {"nombre": "Chocolate Avenida", "precio": 5000, "tipo": "Tabletas", "stock": 100, "descripcion": "Chocolate premium con avellanas"},
    {"nombre": "Chocolate con Leche", "precio": 4000, "tipo": "Tabletas", "stock": 100, "descripcion": "Suave y cremoso, 35% cacao"},
    {"nombre": "Chocolate Blanco", "precio": 6000, "tipo": "Tabletas", "stock": 100, "descripcion": "Delicado chocolate blanco"},
    {"nombre": "Chocolate con Almendras", "precio": 7000, "tipo": "Tabletas", "stock": 100, "descripcion": "Con trozos de almendras tostadas"},
    {"nombre": "Bombones Chocolate Negro", "precio": 8000, "tipo": "Bombones", "stock": 100, "descripcion": "Bombones rellenos de chocolate negro"},
    {"nombre": "Bombones Chocolate Blanco", "precio": 5000, "tipo": "Bombones", "stock": 100, "descripcion": "Bombones de chocolate blanco"},
    {"nombre": "Alfajores", "precio": 5500, "tipo": "Alfajores", "stock": 30, "descripcion": "Con manjar casero"},
    {"nombre": "Macaroons", "precio": 7500, "tipo": "Macaroons", "stock": 8, "descripcion": "Colores y sabores variados"},
]

# 3. Insertar en la base de datos
db = SessionLocal()

try:
    print("=" * 60)
    print("🍫 LLENANDO BASE DE DATOS - CHOCOMANÍA")
    print("=" * 60)
    
    # ✅ BORRAR productos existentes (para evitar duplicados)
    print("\n🗑️ Limpiando productos existentes...")
    db.query(PromocionDB).delete()
    db.query(ProductoDB).delete()
    db.commit()
    print("✅ Base de datos limpia")
    
    print("\n📦 INSERTANDO PRODUCTOS...")
    print("-" * 60)
    
    for item in productos_iniciales:
        nuevo_producto = ProductoDB(
            nombre=item["nombre"],
            precio=item["precio"],
            tipo=item["tipo"],
            stock=item["stock"],
            activo=True,
            descripcion=item["descripcion"]
        )
        db.add(nuevo_producto)
        print(f"  ✅ {item['nombre']}")
        print(f"     Tipo: {item['tipo']} | Precio: ${item['precio']} | Stock: {item['stock']}")
    
    db.commit()
    
    # ✅ CREAR 2 PROMOCIONES
    print("\n🔥 CREANDO PROMOCIONES...")
    print("-" * 60)
    
    # Promoción 1: Bombones Chocolate Negro
    bombones_negro = db.query(ProductoDB).filter(ProductoDB.nombre == "Bombones Chocolate Negro").first()
    if bombones_negro:
        promo1 = PromocionDB(
            producto_id=bombones_negro.id,
            precio_oferta=6000,  # Antes $8000, ahora $6000 (25% OFF)
            fecha_inicio=datetime.now(timezone.utc),
            fecha_termino=datetime.now(timezone.utc) + timedelta(days=30),
            activo=True
        )
        db.add(promo1)
        print(f"  ✅ Promoción: {bombones_negro.nombre}")
        print(f"     ${bombones_negro.precio} → $6000 (25% OFF)")
    
    # Promoción 2: Chocolate con Almendras
    chocolate_almendras = db.query(ProductoDB).filter(ProductoDB.nombre == "Chocolate con Almendras").first()
    if chocolate_almendras:
        promo2 = PromocionDB(
            producto_id=chocolate_almendras.id,
            precio_oferta=5500,  # Antes $7000, ahora $5500 (21% OFF)
            fecha_inicio=datetime.now(timezone.utc),
            fecha_termino=datetime.now(timezone.utc) + timedelta(days=15),
            activo=True
        )
        db.add(promo2)
        print(f"  ✅ Promoción: {chocolate_almendras.nombre}")
        print(f"     ${chocolate_almendras.precio} → $5500 (21% OFF)")
    
    db.commit()
    
    print("\n" + "=" * 60)
    print("✅ ¡CARGA COMPLETADA CON ÉXITO!")
    print("=" * 60)
    print("\n📊 RESUMEN:")
    print(f"   - {len(productos_iniciales)} productos creados")
    print(f"   - 2 promociones activas")
    print("\n🌐 Ahora los 3 catálogos mostrarán estos productos:")
    print("   - Catalogo.html")
    print("   - FiltroCatalogo.html")
    print("   - ActualizacionCatalogo.html")
    print("\n🎨 MAPEO DE IMÁGENES:")
    print("   - Chocolate Avenida → ChocolateAvenida.png")
    print("   - Chocolate con Leche → ChocolateLeche.png")
    print("   - Chocolate Blanco → ChocolateBlanco.png")
    print("   - Chocolate con Almendras → ChocolateAlmendras.png")
    print("   - Bombones Chocolate Negro → Bombones.png")
    print("   - Bombones Chocolate Blanco → BombonesBlanco.png")
    print("   - Alfajores → Alfajores.png")
    print("   - Macaroons → Macaroons.png")
    print("\n" + "=" * 60)

except Exception as e:
    print(f"\n❌ Error: {e}")
    db.rollback()
finally:
    db.close()