from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse 
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta, timezone, date, time
from enum import Enum
import io 
import random

# --- IMPORTS DE INTEGRACIÓN ---
import os
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from fastapi.middleware.cors import CORSMiddleware 

# --- ¡AQUÍ ESTÁ EL CAMBIO! (Cargar .env) ---
from dotenv import load_dotenv
load_dotenv() # Carga las variables del archivo .env automáticamente
# -------------------------------------------

# --- LIBRERÍAS DE SEGURIDAD ---
from passlib.context import CryptContext
from jose import JWTError, jwt

# --- IMPORTS DE BASE DE DATOS ---
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Enum as SAEnum, Table, func
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.ext.declarative import declarative_base

# --- CONFIGURACIÓN DE LA BASE DE DATOS ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./chocomania.db" 

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- CONFIGURACIÓN DE EMAIL (MODO SEGURO) ---
# (Ahora leerá automáticamente del archivo .env)
conf = ConnectionConfig(
    MAIL_USERNAME=os.environ.get("MAIL_USERNAME"),
    MAIL_PASSWORD=os.environ.get("MAIL_PASSWORD"), 
    MAIL_FROM=os.environ.get("MAIL_FROM"),        
    MAIL_PORT=587,
    MAIL_SERVER="smtp.gmail.com",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

# --- 1. DEFINICIONES DE ENUMS ---
class Roles(str, Enum):
    cliente = "cliente"
    administrador = "administrador"
    cocinero = "cocinero"
    repartidor = "repartidor"
class EstadoPedido(str, Enum):
    pendiente_de_pago = "pendiente_de_pago"
    pagado = "pagado"
    en_preparacion = "en_preparacion"
    despachado = "despachado"
    entregado = "entregado" 
    rechazado = "rechazado"
    cancelado = "cancelado"
class TipoNotificacion(str, Enum):
    pedido_recibido = "pedido_recibido"
    pedido_despachado = "pedido_despachado"
    retraso_entrega = "retraso_entrega"
class EstadoSeguimiento(str, Enum):
    en_camino = "En Camino"
    entregado = "Entregado"
    problema_reportado = "Problema Reportado"
class TipoDocumento(str, Enum):
    boleta = "boleta"
    factura = "factura"


# --- 2. MODELOS DE BASE DE DATOS (SQLAlchemy) ---
pedido_items_tabla = Table('pedido_items', Base.metadata,
    Column('pedido_id', Integer, ForeignKey('pedidos.id'), primary_key=True),
    Column('producto_id', Integer, ForeignKey('productos.id'), primary_key=True),
    Column('cantidad', Integer),
    Column('precio_en_el_momento', Float)
)
class UsuarioDB(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    rol = Column(SAEnum(Roles), default=Roles.cliente)
    nombre = Column(String, nullable=True)
    direccion = Column(String, nullable=True)
    comuna = Column(String, nullable=True)
    telefono = Column(String, nullable=True)
    recibirPromos = Column(Boolean, default=True)
    pedidos = relationship("PedidoDB", back_populates="dueño")
    carrito = relationship("CarritoDB", back_populates="dueño", uselist=False)
class ProductoDB(Base):
    __tablename__ = "productos"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, index=True)
    descripcion = Column(String, nullable=True)
    precio = Column(Float)
    tipo = Column(String)
    stock = Column(Integer)
    activo = Column(Boolean, default=True)
    pedidos = relationship("PedidoDB", secondary=pedido_items_tabla, back_populates="productos")
    promocion_activa = relationship("PromocionDB", back_populates="producto", uselist=False)
    items_carrito = relationship("CarritoItemDB", back_populates="producto")
class PedidoDB(Base):
    __tablename__ = "pedidos"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey('usuarios.id'))
    total = Column(Float)
    estado = Column(SAEnum(EstadoPedido), default=EstadoPedido.pendiente_de_pago)
    fecha_creacion = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    dueño = relationship("UsuarioDB", back_populates="pedidos")
    productos = relationship("ProductoDB", secondary=pedido_items_tabla, back_populates="pedidos")
    seguimiento = relationship("SeguimientoDB", back_populates="pedido", uselist=False)
    notificaciones = relationship("NotificacionDB", back_populates="pedido")
    documento = relationship("DocumentoDB", back_populates="pedido", uselist=False)
class NotificacionDB(Base):
    __tablename__ = "notificaciones"
    id = Column(Integer, primary_key=True, index=True)
    pedido_id = Column(Integer, ForeignKey('pedidos.id'))
    tipo = Column(SAEnum(TipoNotificacion))
    mensaje = Column(String)
    hora_estimada = Column(String, nullable=True) 
    fecha_envio = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    pedido = relationship("PedidoDB", back_populates="notificaciones")
class SeguimientoDB(Base):
    __tablename__ = "seguimientos"
    id = Column(Integer, primary_key=True, index=True)
    pedido_id = Column(Integer, ForeignKey('pedidos.id'), unique=True)
    estado = Column(SAEnum(EstadoSeguimiento), default=EstadoSeguimiento.en_camino)
    hora_estimada_llegada = Column(String, nullable=True)
    repartidor_asignado = Column(String, nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    pedido = relationship("PedidoDB", back_populates="seguimiento")
class DocumentoDB(Base):
    __tablename__ = "documentos"
    id = Column(Integer, primary_key=True, index=True)
    pedido_id = Column(Integer, ForeignKey('pedidos.id'))
    fecha = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    tipo = Column(SAEnum(TipoDocumento))
    total = Column(Float)
    rut = Column(String, nullable=True)
    razon_social = Column(String, nullable=True)
    pedido = relationship("PedidoDB", back_populates="documento", foreign_keys=[pedido_id])
class PromocionDB(Base):
    __tablename__ = "promociones"
    id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(Integer, ForeignKey('productos.id'))
    precio_oferta = Column(Float)
    fecha_inicio = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    fecha_termino = Column(DateTime(timezone=True))
    activo = Column(Boolean, default=True)
    producto = relationship("ProductoDB", back_populates="promocion_activa")
class CarritoDB(Base):
    __tablename__ = "carritos"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey('usuarios.id'), unique=True) 
    dueño = relationship("UsuarioDB", back_populates="carrito")
    items = relationship("CarritoItemDB", back_populates="carrito", cascade="all, delete-orphan")
class CarritoItemDB(Base):
    __tablename__ = "carrito_items"
    id = Column(Integer, primary_key=True, index=True)
    carrito_id = Column(Integer, ForeignKey('carritos.id'))
    producto_id = Column(Integer, ForeignKey('productos.id'))
    cantidad = Column(Integer)
    carrito = relationship("CarritoDB", back_populates="items")
    producto = relationship("ProductoDB", back_populates="items_carrito")


# --- 3. SCHEMAS (DTOs de Pydantic) ---
class UsuarioCreate(BaseModel):
    email: str
    contraseña: str
class DatosPersonalesUpdate(BaseModel):
    nombre: str
    direccion: str
    comuna: str
    telefono: str
class SuscripcionInput(BaseModel):
    recibirPromos: bool
class CambioContraseñaInput(BaseModel):
    contraseña_actual: str
    nueva_contraseña: str
class RolUpdate(BaseModel):
    nuevo_rol: Roles
class ProductoBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    precio: float
    tipo: str
    stock: int
class ProductoCreate(ProductoBase):
    pass
class ProductoUpdate(BaseModel):
    activo: Optional[bool] = None
class PedidoItemInput(BaseModel): 
    producto_id: int
    cantidad: int
class EnviarNotificacionInput(BaseModel):
    pedido_id: int
    tipo: TipoNotificacion
    mensaje_opcional: Optional[str] = None
class ActualizarNotificacionInput(BaseModel):
    mensaje_nuevo: str
    nueva_hora_estimada: Optional[time] = None
class Ubicacion(BaseModel):
    lat: float
    lng: float
class ConfirmarEntregaInput(BaseModel):
    confirmacion_texto: str = "Entregado OK" 
class FacturaInput(BaseModel):
    rut: str
    razon_social: str
class VentasPorHora(BaseModel):
    hora: int
    total: float
class DashboardVentas(BaseModel):
    total_acumulado: float
    ticket_promedio: float
    top_productos: List[str]
    ventas_por_hora: List[VentasPorHora]
class DashboardPedidoActivo(BaseModel):
    id: str
    cliente: str
    estado: str
    tiempo_estimado: str
    encargado: str
class PromocionCreate(BaseModel):
    producto_id: int
    precio_oferta: float
    fecha_termino: datetime 
class CarritoItemCreate(BaseModel):
    producto_id: int
    cantidad: int
class ConfigORM:
    from_attributes = True 
class UsuarioSchema(BaseModel):
    id: int
    email: str
    rol: Roles
    nombre: Optional[str] = None
    direccion: Optional[str] = None
    comuna: Optional[str] = None
    telefono: Optional[str] = None
    recibirPromos: bool
    class Config(ConfigORM): pass
class ProductoSchema(ProductoBase):
    id: int
    activo: bool
    class Config(ConfigORM): pass
class PedidoSchema(BaseModel):
    id: int
    usuario_id: int
    total: float
    estado: EstadoPedido
    fecha_creacion: datetime
    class Config(ConfigORM): pass
class SeguimientoSchema(BaseModel):
    pedido_id: int 
    estado: EstadoSeguimiento
    ubicacion_actual: Optional[Ubicacion] = None
    class Config(ConfigORM): pass
class NotificacionSchema(BaseModel):
    id: int
    pedido_id: int
    tipo: TipoNotificacion
    mensaje: str
    fecha_envio: datetime
    class Config(ConfigORM): pass
class DocumentoSchema(BaseModel):
    id: int
    pedido_id: int
    tipo: TipoDocumento
    total: float
    rut: Optional[str] = None
    razon_social: Optional[str] = None
    class Config(ConfigORM): pass
class PromocionSchema(BaseModel):
    id: int
    producto_id: int
    precio_oferta: float
    fecha_termino: datetime
    activo: bool
    class Config(ConfigORM): pass
class CarritoItemSchema(BaseModel):
    id: int
    producto_id: int
    cantidad: int
    producto: ProductoSchema 
    class Config(ConfigORM): pass
class CarritoSchema(BaseModel):
    id: int
    usuario_id: int
    items: List[CarritoItemSchema] = []
    total_calculado: float = 0.0 
    class Config(ConfigORM): pass


# --- 4. CONFIGURACIÓN DE SEGURIDAD ---
SECRET_KEY = "tu-clave-secreta-super-dificil-de-adivinar"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- 5. FUNCIONES HELPER DE SEGURIDAD ---
def verificar_contraseña(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
def hashear_contraseña(password: str) -> str:
    return pwd_context.hash(password)
def crear_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta: expire = datetime.now(timezone.utc) + expires_delta
    else: expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- 6. FUNCIONES DE AUTENTICACIÓN Y BBDD ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
def get_usuario_by_email(db: Session, email: str) -> Optional[UsuarioDB]:
    return db.query(UsuarioDB).filter(UsuarioDB.email == email).first()
def get_usuario_by_id(db: Session, user_id: int) -> Optional[UsuarioDB]:
    return db.query(UsuarioDB).filter(UsuarioDB.id == user_id).first()
def get_producto_by_id(db: Session, producto_id: int) -> Optional[ProductoDB]:
    return db.query(ProductoDB).filter(ProductoDB.id == producto_id).first()
def get_pedido_by_id(db: Session, pedido_id: int) -> Optional[PedidoDB]:
    return db.query(PedidoDB).filter(PedidoDB.id == pedido_id).first()
def get_notificacion_by_pedido_id(db: Session, pedido_id: int) -> List[NotificacionDB]:
    return db.query(NotificacionDB).filter(NotificacionDB.pedido_id == pedido_id).all()
def get_seguimiento_by_pedido_id(db: Session, pedido_id: int) -> Optional[SeguimientoDB]:
    return db.query(SeguimientoDB).filter(SeguimientoDB.pedido_id == pedido_id).first()
def get_carrito_by_user_id(db: Session, usuario_id: int) -> Optional[CarritoDB]:
    return db.query(CarritoDB).filter(CarritoDB.usuario_id == usuario_id).first()
def get_or_create_carrito(db: Session, usuario_id: int) -> CarritoDB:
    carrito = get_carrito_by_user_id(db, usuario_id)
    if not carrito:
        carrito = CarritoDB(usuario_id=usuario_id)
        db.add(carrito)
        db.commit()
        db.refresh(carrito)
    return carrito
def autenticar_usuario(db: Session, email: str, contraseña: str) -> Optional[UsuarioDB]:
    usuario = get_usuario_by_email(db, email)
    if not usuario or not verificar_contraseña(contraseña, usuario.hashed_password):
        return None
    return usuario
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> UsuarioDB:
    credentials_exception = HTTPException(status_code=401, detail="Credenciales inválidas")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None: raise credentials_exception
    except JWTError:
        raise credentials_exception
    usuario = get_usuario_by_email(db, email) 
    if usuario is None: raise credentials_exception
    return usuario
async def get_current_admin_user(current_user: UsuarioDB = Depends(get_current_user)) -> UsuarioDB:
    if current_user.rol != Roles.administrador:
        raise HTTPException(status_code=403, detail="Requiere permisos de administrador")
    return current_user
async def get_current_repartidor_user(current_user: UsuarioDB = Depends(get_current_user)) -> UsuarioDB:
    if current_user.rol != Roles.repartidor:
        raise HTTPException(status_code=403, detail="Acción solo para repartidores")
    return current_user

# --- 7. CREA LA APP ---
app = FastAPI(
    title="Chocomanía API (v7 - CON EMAIL)",
    description="API para el sistema de E-commerce Chocomanía"
)

# ¡ESTA LÍNEA CREA EL ARCHIVO 'chocomania.db' Y LAS TABLAS!
Base.metadata.create_all(bind=engine)

# --- 8. FUNCIÓN HELPER PARA ENVIAR EMAIL (NUEVA) ---
async def enviar_email_async(asunto: str, email_destinatario: str, cuerpo_html: str):
    """
    Envía un email de forma asíncrona.
    """
    # Evita enviar correos si las credenciales no están configuradas
    if not conf.MAIL_USERNAME or not conf.MAIL_PASSWORD:
        print(f"--- SIMULACIÓN DE EMAIL (NO CONFIGURADO) ---")
        print(f"PARA: {email_destinatario}")
        print(f"ASUNTO: {asunto}")
        print(f"---------------------------------------------")
        return

    message = MessageSchema(
        subject=asunto,
        recipients=[email_destinatario],
        body=cuerpo_html,
        subtype="html"
    )
    
    fm = FastMail(conf)
    try:
        await fm.send_message(message)
        print(f"Email enviado a {email_destinatario} (Asunto: {asunto})")
    except Exception as e:
        print(f"ERROR AL ENVIAR EMAIL: {e}")

# --- 9. CONFIGURACIÓN DE CORS (NUEVA) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Permite que tu "Login.html" (file://) se conecte
    allow_credentials=True,
    allow_methods=["*"], # Permite POST, GET, etc.
    allow_headers=["*"], # Permite "Content-Type"
)

# --- 10. ENDPOINTS (API) ---

@app.get("/")
def leer_root(): return {"mensaje": "¡Bienvenido a la API de Chocomanía!"}


# --- ENDPOINTS DE USUARIO Y AUTENTICACIÓN ---

# ¡MODIFICADO! (Ahora es "async def")
@app.post("/usuarios/registrar", response_model=UsuarioSchema, status_code=201)
async def registrar_usuario(usuario_input: UsuarioCreate, db: Session = Depends(get_db)):
    if get_usuario_by_email(db, usuario_input.email):
        raise HTTPException(status_code=400, detail="El Email esta en uso")
    hashed_password = hashear_contraseña(usuario_input.contraseña)
    rol_asignado = Roles.cliente
    user_count = db.query(UsuarioDB).count()
    if user_count == 0:
        rol_asignado = Roles.administrador
        print(f"¡TESTING!: Usuario {usuario_input.email} creado como ADMINISTRADOR.")
    nuevo_usuario_db = UsuarioDB(email=usuario_input.email, hashed_password=hashed_password, rol=rol_asignado)
    db.add(nuevo_usuario_db)
    db.commit()
    db.refresh(nuevo_usuario_db)
    
    # --- ¡LÓGICA DE EMAIL AÑADIDA! ---
    cuerpo_html = f"""
    <h1>¡Bienvenido a Chocomanía, {usuario_input.email}!</h1>
    <p>Tu cuenta ha sido creada exitosamente.</p>
    <p>Ya puedes empezar a comprar.</p>
    """
    await enviar_email_async(
        asunto="¡Bienvenido a Chocomanía!",
        email_destinatario=usuario_input.email,
        cuerpo_html=cuerpo_html
    )
    # --- FIN ---
    return nuevo_usuario_db

@app.post("/token", response_model=dict)
def login_para_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    usuario = autenticar_usuario(db, form_data.username, form_data.password)
    if not usuario:
        raise HTTPException(status_code=401, detail="Email o contraseña incorrecta", headers={"WWW-Authenticate": "Bearer"})
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = crear_access_token(data={"sub": usuario.email}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/usuarios/me", response_model=UsuarioSchema)
async def leer_mi_perfil(current_user: UsuarioDB = Depends(get_current_user)):
    return current_user

@app.put("/usuarios/me/password")
def cambiar_contraseña(input: CambioContraseñaInput, current_user: UsuarioDB = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verificar_contraseña(input.contraseña_actual, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta")
    current_user.hashed_password = hashear_contraseña(input.nueva_contraseña)
    db.commit()
    return {"mensaje": "Contraseña actualizada exitosamente"}

# Endpoint para listar todos los usuarios (Solo Admin)
@app.get("/admin/usuarios", response_model=List[UsuarioSchema])
def listar_usuarios(
    admin_user: UsuarioDB = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Obtiene la lista completa de usuarios registrados.
    Requiere rol de administrador.
    """
    usuarios = db.query(UsuarioDB).all()
    return usuarios

# 1. Primero, define este esquema pequeño (puedes ponerlo junto a los otros schemas o justo antes del endpoint)
class RolInput(BaseModel):
    rol: Roles  # Coincide con lo que envía el HTML: JSON.stringify({ rol: nuevoRol })

# 2. Reemplaza el endpoint completo por este:
@app.put("/admin/usuarios/{usuario_id}/asignar-rol", response_model=UsuarioSchema)
def asignar_rol(
    usuario_id: int, 
    rol_input: RolInput, 
    admin_user: UsuarioDB = Depends(get_current_admin_user), 
    db: Session = Depends(get_db)
):
    # Buscar usuario
    usuario = get_usuario_by_id(db, usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Protección: Evitar que el admin se quite el rol a sí mismo por accidente
    if usuario.id == admin_user.id and rol_input.rol != Roles.administrador:
        raise HTTPException(status_code=400, detail="No puedes quitarte el rol de administrador a ti mismo")

    # Actualizar
    usuario.rol = rol_input.rol
    db.commit()
    db.refresh(usuario)
    
    return usuario

@app.put("/usuarios/me/datos", response_model=UsuarioSchema)
def actualizar_datos_personales(datos: DatosPersonalesUpdate, current_user: UsuarioDB = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.nombre = datos.nombre
    current_user.direccion = datos.direccion
    current_user.comuna = datos.comuna
    current_user.telefono = datos.telefono
    db.commit()
    db.refresh(current_user)
    return current_user

# ¡MODIFICADO! (Ahora es "async def")
@app.put("/usuarios/me/suscripcion", response_model=UsuarioSchema)
async def gestionar_suscripcion(suscripcion: SuscripcionInput, current_user: UsuarioDB = Depends(get_current_user), db: Session = Depends(get_db)):
    
    era_suscrito = current_user.recibirPromos
    esta_suscrito = suscripcion.recibirPromos
    current_user.recibirPromos = esta_suscrito
    db.commit()
    db.refresh(current_user)

    # Si el usuario ACABA de suscribirse...
    if esta_suscrito and not era_suscrito:
        cuerpo_html = f"""
        <h1>¡Gracias por suscribirte a Chocomanía! 🍫</h1>
        <p>Hola {current_user.nombre or current_user.email},</p>
        <p>Ahora estás en nuestra lista exclusiva. Serás el primero en enterarte de nuestras ofertas.</p>
        """
        await enviar_email_async(
            asunto="¡Suscripción confirmada! - Chocomanía",
            email_destinatario=current_user.email,
            cuerpo_html=cuerpo_html
        )
    return current_user

# --- ENDPOINTS DE CATÁLOGO (Productos) ---
@app.post("/productos/", response_model=ProductoSchema, status_code=201)
def crear_producto(producto_input: ProductoCreate, admin_user: UsuarioDB = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    nuevo_producto_db = ProductoDB(**producto_input.model_dump(), activo=True) 
    db.add(nuevo_producto_db)
    db.commit()
    db.refresh(nuevo_producto_db)
    return nuevo_producto_db

@app.get("/productos/", response_model=List[ProductoSchema])
def leer_productos(tipo: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(ProductoDB).filter(ProductoDB.activo == True)
    if tipo:
        query = query.filter(ProductoDB.tipo.ilike(f"%{tipo}%")) 
    return query.all()

@app.put("/productos/{producto_id}", response_model=ProductoSchema)
def actualizar_producto(producto_id: int, producto_update: ProductoUpdate, admin_user: UsuarioDB = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    producto = get_producto_by_id(db, producto_id)
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    update_data = producto_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(producto, key, value)
    db.commit()
    db.refresh(producto)
    return producto


# --- ENDPOINTS DE PROMOCIONES (B-06) ---
@app.post("/admin/promociones/", response_model=PromocionSchema, status_code=201)
def crear_promocion(promo_input: PromocionCreate, admin_user: UsuarioDB = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    producto = get_producto_by_id(db, promo_input.producto_id)
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado para la promoción")
    nueva_promo = PromocionDB(
        producto_id=promo_input.producto_id,
        precio_oferta=promo_input.precio_oferta,
        fecha_termino=promo_input.fecha_termino,
        activo=True
    )
    db.add(nueva_promo)
    db.commit()
    db.refresh(nueva_promo)
    return nueva_promo

@app.get("/promociones/activas", response_model=List[dict])
def leer_promociones_activas(db: Session = Depends(get_db)):
    """
    Obtiene promociones activas con información completa del producto.
    """
    ahora = datetime.now(timezone.utc)
    
    print(f"🔍 Buscando promociones activas después de: {ahora}")
    
    promociones = db.query(PromocionDB).filter(
        PromocionDB.activo == True,
        PromocionDB.fecha_termino > ahora
    ).all()
    
    print(f"✅ Promociones encontradas en BD: {len(promociones)}")
    
    result = []
    for promo in promociones:
        producto = get_producto_by_id(db, promo.producto_id)
        
        if not producto:
            print(f"⚠️ Producto {promo.producto_id} no encontrado")
            continue
            
        if not producto.activo:
            print(f"⚠️ Producto {producto.nombre} está inactivo")
            continue
        
        descuento = round(((producto.precio - promo.precio_oferta) / producto.precio) * 100)
        dias_restantes = max((promo.fecha_termino - ahora).days, 0)
        
        promo_data = {
            "id": promo.id,
            "producto_id": promo.producto_id,
            "producto_nombre": producto.nombre,
            "producto_descripcion": producto.descripcion or "Delicioso chocolate artesanal",
            "precio_original": producto.precio,
            "precio_oferta": promo.precio_oferta,
            "descuento_porcentaje": descuento,
            "fecha_termino": promo.fecha_termino.isoformat(),
            "dias_restantes": dias_restantes
        }
        
        print(f"📦 Promoción {promo.id}: {producto.nombre} - {descuento}% OFF (${promo.precio_oferta})")
        result.append(promo_data)
    
    print(f"📤 Enviando {len(result)} promociones al frontend")
    return result


# --- (B-11) ENDPOINTS DE CARRITO ---
def _calcular_total_carrito(carrito: CarritoDB, db: Session) -> float:
    total = 0.0
    for item in carrito.items:
        producto = get_producto_by_id(db, item.producto_id)
        if not producto or not producto.activo:
            continue
        precio_a_cobrar = producto.precio 
        promo_activa = db.query(PromocionDB).filter(
            PromocionDB.producto_id == producto.id,
            PromocionDB.activo == True,
            PromocionDB.fecha_termino > datetime.now(timezone.utc)
        ).first()
        if promo_activa:
            precio_a_cobrar = promo_activa.precio_oferta
        total += precio_a_cobrar * item.cantidad
    return total

@app.get("/carrito/me", response_model=CarritoSchema)
def get_mi_carrito(
    current_user: UsuarioDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    carrito = get_or_create_carrito(db, current_user.id)
    total = _calcular_total_carrito(carrito, db)
    response_schema = CarritoSchema.from_orm(carrito) 
    response_schema.total_calculado = total
    return response_schema

@app.post("/carrito/items", response_model=CarritoSchema)
def agregar_item_al_carrito(
    item_input: CarritoItemCreate,
    current_user: UsuarioDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    carrito = get_or_create_carrito(db, current_user.id)
    producto = get_producto_by_id(db, item_input.producto_id)
    if not producto or not producto.activo:
        raise HTTPException(status_code=404, detail="Producto no encontrado o inactivo")
    if producto.stock < item_input.cantidad:
        raise HTTPException(status_code=400, detail="No hay stock suficiente")
    item_existente = db.query(CarritoItemDB).filter(
        CarritoItemDB.carrito_id == carrito.id,
        CarritoItemDB.producto_id == item_input.producto_id
    ).first()
    if item_existente:
        item_existente.cantidad += item_input.cantidad
    else:
        nuevo_item = CarritoItemDB(
            carrito_id=carrito.id,
            producto_id=item_input.producto_id,
            cantidad=item_input.cantidad
        )
        db.add(nuevo_item)
    db.commit()
    db.refresh(carrito)
    total = _calcular_total_carrito(carrito, db)
    response_schema = CarritoSchema.from_orm(carrito)
    response_schema.total_calculado = total
    return response_schema

@app.delete("/carrito/items/{item_id}", response_model=CarritoSchema)
def eliminar_item_del_carrito(
    item_id: int,
    current_user: UsuarioDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    carrito = get_carrito_by_user_id(db, current_user.id)
    if not carrito:
        raise HTTPException(status_code=404, detail="Carrito no encontrado")
    item_a_eliminar = db.query(CarritoItemDB).filter(
        CarritoItemDB.id == item_id,
        CarritoItemDB.carrito_id == carrito.id
    ).first()
    if not item_a_eliminar:
        raise HTTPException(status_code=404, detail="Item no encontrado en el carrito")
    db.delete(item_a_eliminar)
    db.commit()
    db.refresh(carrito)
    total = _calcular_total_carrito(carrito, db)
    response_schema = CarritoSchema.from_orm(carrito)
    response_schema.total_calculado = total
    return response_schema

@app.delete("/carrito", response_model=dict)
def vaciar_carrito(
    current_user: UsuarioDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    carrito = get_carrito_by_user_id(db, current_user.id)
    if not carrito:
        return {"mensaje": "El carrito ya estaba vacío"}
    db.query(CarritoItemDB).filter(CarritoItemDB.carrito_id == carrito.id).delete()
    db.commit()
    return {"mensaje": "Carrito vaciado exitosamente"}


# --- ENDPOINTS DE PAGO Y PEDIDOS ---

# ¡MODIFICADO! (Con el ARREGLO CRÍTICO)
@app.post("/pedidos/crear-pago-desde-carrito", response_model=dict)
async def crear_pedido_y_pago_desde_carrito(
    current_user: UsuarioDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    (REFACTOR de B-08)
    Crea un Pedido usando los items del CarritoDB del usuario.
    """
    
    # 1. Obtener Carrito
    carrito = get_carrito_by_user_id(db, current_user.id)
    if not carrito or not carrito.items:
        raise HTTPException(status_code=400, detail="El carrito está vacío") # Gherkin B-08

    # 2. Validar stock y calcular total
    total_calculado = 0.0
    
    # (Este primer bucle es solo para validación y calcular el total)
    for item in carrito.items:
        producto = get_producto_by_id(db, item.producto_id)
        if not producto or not producto.activo:
             raise HTTPException(status_code=400, detail=f"Producto {item.producto_id} ya no está disponible")
        if producto.stock < item.cantidad:
             raise HTTPException(status_code=400, detail=f"No hay stock suficiente de {producto.nombre}")
        
        promo_activa = db.query(PromocionDB).filter(PromocionDB.producto_id == producto.id, PromocionDB.activo == True, PromocionDB.fecha_termino > datetime.now(timezone.utc)).first()
        precio_a_cobrar = promo_activa.precio_oferta if promo_activa else producto.precio
        
        total_calculado += precio_a_cobrar * item.cantidad
        
    # 3. Crear el Pedido en BBDD
    nuevo_pedido_db = PedidoDB(
        usuario_id=current_user.id,
        total=total_calculado,
        estado=EstadoPedido.pendiente_de_pago
    )
    db.add(nuevo_pedido_db)
    
    # --- ¡AQUÍ ESTÁ EL ARREGLO IMPORTANTE! ---
    
    # Hacemos "flush" para obtener el ID del nuevo pedido (nuevo_pedido_db.id)
    db.flush()

    # 3b. (Bucle 2) Ahora copiamos los items del carrito a la tabla de pedidos
    for item in carrito.items:
        # Volvemos a calcular el precio de este item (para guardarlo en el historial)
        producto = get_producto_by_id(db, item.producto_id)
        promo_activa = db.query(PromocionDB).filter(
            PromocionDB.producto_id == producto.id,
            PromocionDB.activo == True,
            PromocionDB.fecha_termino > datetime.now(timezone.utc)
        ).first()
        precio_en_el_momento = promo_activa.precio_oferta if promo_activa else producto.precio
        
        # Insertamos la relación en la tabla asociativa
        db.execute(pedido_items_tabla.insert().values(
            pedido_id=nuevo_pedido_db.id,
            producto_id=item.producto_id,
            cantidad=item.cantidad,
            precio_en_el_momento=precio_en_el_momento
        ))
    
    # --- ¡FIN DEL ARREGLO! ---
    
    # 4. Vaciar el carrito (ahora que los items están copiados)
    db.query(CarritoItemDB).filter(CarritoItemDB.carrito_id == carrito.id).delete()

    # 5. Confirmar todos los cambios
    db.commit()
    db.refresh(nuevo_pedido_db)
    
    # Retornar el ID del pedido creado
    return {
        "ok": True,
        "pedido_id": str(nuevo_pedido_db.id),  # ← Asegurar que sea string
        "redirect_url": f"ConfirmacionPago.html?order_id={nuevo_pedido_db.id}"
    }


# ¡MODIFICADO! (Ahora guarda los datos y responde con DocumentoSchema)
@app.post("/pedidos/{pedido_id}/solicitar-factura", response_model=DocumentoSchema)
def solicitar_factura(pedido_id: int, factura_input: FacturaInput, current_user: UsuarioDB = Depends(get_current_user), db: Session = Depends(get_db)):
    pedido = get_pedido_by_id(db, pedido_id)
    if not pedido or pedido.usuario_id != current_user.id:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    # Busca el documento que se creó en el pago
    doc = db.query(DocumentoDB).filter(DocumentoDB.pedido_id == pedido_id).first()
    
    if not doc:
        # Si no existe por algún motivo, lo crea
        doc = DocumentoDB(
            pedido_id=pedido.id, 
            total=pedido.total,
            tipo=TipoDocumento.factura,
            rut=factura_input.rut,
            razon_social=factura_input.razon_social
        )
        db.add(doc)
    else:
        # Si ya existía (como boleta), lo actualiza a factura
        doc.tipo = TipoDocumento.factura
        doc.rut = factura_input.rut
        doc.razon_social = factura_input.razon_social
            
    db.commit()
    db.refresh(doc)
    print(f"Documento {doc.id} para Pedido {pedido_id} actualizado a FACTURA con RUT {factura_input.rut}")
    
    return doc

# ¡MODIFICADO! (Ahora es "async def")
@app.get("/pagos/confirmacion", response_model=dict)
async def confirmar_pago_simulado(token: int, simul_status: str, db: Session = Depends(get_db)):
    pedido = get_pedido_by_id(db, token)
    if not pedido or pedido.estado != EstadoPedido.pendiente_de_pago:
        raise HTTPException(status_code=404, detail="Pedido no válido o ya procesado")

    if simul_status == "aprobado":
        # ✅ CAMBIO: Cambiar a "pagado" primero, luego a "en_preparacion"
        pedido.estado = EstadoPedido.pagado
        print(f"Pedido {pedido.id} ahora PAGADO.")
        
        # Crea el documento por defecto como BOLETA
        nuevo_doc = DocumentoDB(pedido_id=pedido.id, tipo=TipoDocumento.boleta, total=pedido.total)
        db.add(nuevo_doc)
        
        nuevo_seguimiento = SeguimientoDB(
            pedido_id=pedido.id,
            estado=EstadoSeguimiento.en_camino,
            hora_estimada_llegada= (datetime.now(timezone.utc) + timedelta(hours=1)).time().isoformat()
        )
        db.add(nuevo_seguimiento)
        
        # --- ¡LÓGICA DE EMAIL AÑADIDA! ---
        dueño_pedido = get_usuario_by_id(db, pedido.usuario_id)
        if dueño_pedido:
            cuerpo_html = f"""
            <h1>¡Tu pago ha sido aprobado!</h1>
            <p>Hola {dueño_pedido.nombre or dueño_pedido.email},</p>
            <p>Tu pago para el pedido <strong>Nº {pedido.id}</strong> por un total de <strong>${pedido.total}</strong> ha sido procesado.</p>
            <p>Ya estamos preparando tus chocolates.</p>
            <p>¡Gracias por tu compra!</p>
            """
            await enviar_email_async(
                asunto=f"Confirmación de Pedido Chocomanía Nº {pedido.id}",
                email_destinatario=dueño_pedido.email,
                cuerpo_html=cuerpo_html
            )
        # --- FIN ---
        
        db.commit()
        return {
            "mensaje": "Pago aprobado.",
            "estado": "pagado",
            "pedido_id": pedido.id
        }
    else:
        pedido.estado = EstadoPedido.rechazado
        db.commit()
        return {
            "mensaje": "Transacción no autorizada",
            "estado": "rechazado"
        }

@app.put("/pedidos/{pedido_id}/cancelar", response_model=PedidoSchema)
def cancelar_pedido(pedido_id: int, current_user: UsuarioDB = Depends(get_current_user), db: Session = Depends(get_db)):
    pedido = get_pedido_by_id(db, pedido_id)
    if not pedido or pedido.usuario_id != current_user.id:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    if pedido.estado in [EstadoPedido.despachado, EstadoPedido.entregado]:
        raise HTTPException(status_code=400, detail="No se puede cancelar, el pedido ya fue despachado")
    pedido.estado = EstadoPedido.cancelado
    db.commit()
    print(f"Pedido {pedido.id} marcado como CANCELADO.")
    return pedido

# ¡NUEVO ENDPOINT! Marcar pedido como pagado
@app.put("/pedidos/{pedido_id}/pagar", response_model=dict)
async def marcar_pedido_pagado(
    pedido_id: int,
    current_user: UsuarioDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Marca un pedido como pagado (simula confirmación de pago).
    """
    pedido = get_pedido_by_id(db, pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    if pedido.usuario_id != current_user.id:
        raise HTTPException(status_code=403, detail="No tienes permiso para este pedido")
    
    if pedido.estado != EstadoPedido.pendiente_de_pago:
        # Si ya está pagado, retornar éxito igual
        return {
            "mensaje": "Pedido ya procesado",
            "estado": pedido.estado.value,
            "pedido_id": pedido.id
        }
    
    # Cambiar estado a PAGADO
    pedido.estado = EstadoPedido.pagado
    print(f"Pedido {pedido.id} marcado como PAGADO.")
    
    # Crear documento (boleta) si no existe
    doc_existente = db.query(DocumentoDB).filter(DocumentoDB.pedido_id == pedido_id).first()
    if not doc_existente:
        nuevo_doc = DocumentoDB(pedido_id=pedido.id, tipo=TipoDocumento.boleta, total=pedido.total)
        db.add(nuevo_doc)
    
    # Crear seguimiento si no existe
    seguimiento_existente = get_seguimiento_by_pedido_id(db, pedido_id)
    if not seguimiento_existente:
        nuevo_seguimiento = SeguimientoDB(
            pedido_id=pedido.id,
            estado=EstadoSeguimiento.en_camino,
            hora_estimada_llegada=(datetime.now(timezone.utc) + timedelta(hours=1)).time().isoformat()
        )
        db.add(nuevo_seguimiento)
    
    db.commit()
    db.refresh(pedido)
    
    # Enviar email de confirmación
    cuerpo_html = f"""
    <h1>¡Tu pago ha sido aprobado!</h1>
    <p>Hola {current_user.nombre or current_user.email},</p>
    <p>Tu pago para el pedido <strong>Nº {pedido.id}</strong> por un total de <strong>${pedido.total}</strong> ha sido procesado.</p>
    <p>Ya estamos preparando tus chocolates.</p>
    <p>¡Gracias por tu compra!</p>
    """
    await enviar_email_async(
        asunto=f"Confirmación de Pedido Chocomanía Nº {pedido.id}",
        email_destinatario=current_user.email,
        cuerpo_html=cuerpo_html
    )
    
    return {
        "mensaje": "Pago aprobado exitosamente",
        "estado": "pagado",
        "pedido_id": pedido.id
    }

# ¡NUEVO! Schema para actualizar estado de pedido
class EstadoPedidoInput(BaseModel):
    estado: EstadoPedido

# ¡NUEVO ENDPOINT! PUT para actualizar estado de pedido
@app.put("/pedidos/{pedido_id}", response_model=PedidoSchema)
def actualizar_estado_pedido(
    pedido_id: int,
    estado_input: EstadoPedidoInput,
    current_user: UsuarioDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Actualiza el estado de un pedido.
    """
    pedido = get_pedido_by_id(db, pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    # Verificar permisos
    if current_user.rol != Roles.administrador and pedido.usuario_id != current_user.id:
        raise HTTPException(status_code=403, detail="No tienes permiso para modificar este pedido")
    
    # Actualizar estado
    pedido.estado = estado_input.estado
    db.commit()
    db.refresh(pedido)
    
    print(f"Pedido {pedido_id} actualizado a estado: {estado_input.estado.value}")
    return pedido

# ¡NUEVO ENDPOINT! PATCH para actualizar estado de pedido
@app.patch("/pedidos/{pedido_id}", response_model=PedidoSchema)
def actualizar_pedido_parcial(
    pedido_id: int,
    estado_input: EstadoPedidoInput,
    current_user: UsuarioDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Actualiza parcialmente un pedido (PATCH).
    """
    return actualizar_estado_pedido(pedido_id, estado_input, current_user, db)

# ¡NUEVO ENDPOINT! Obtener pedidos sin repartidor asignado (Admin)
@app.get("/admin/pedidos/sin-asignar", response_model=List[dict])
def obtener_pedidos_sin_asignar(
    admin_user: UsuarioDB = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Obtiene todos los pedidos pagados o en preparación sin repartidor asignado.
    """
    estados_para_asignar = [EstadoPedido.pagado, EstadoPedido.en_preparacion]
    
    pedidos = db.query(PedidoDB).filter(
        PedidoDB.estado.in_(estados_para_asignar)
    ).all()
    
    result = []
    for pedido in pedidos:
        # Verificar si tiene seguimiento y repartidor asignado
        seguimiento = get_seguimiento_by_pedido_id(db, pedido.id)
        
        # Solo incluir si no tiene repartidor asignado
        if not seguimiento or not seguimiento.repartidor_asignado:
            cliente = get_usuario_by_id(db, pedido.usuario_id)
            result.append({
                "id": pedido.id,
                "clientName": cliente.nombre if cliente and cliente.nombre else "Cliente",
                "total": pedido.total,
                "estado": pedido.estado.value,
                "fecha_creacion": pedido.fecha_creacion.isoformat() if pedido.fecha_creacion else None
            })
    
    return result

# ¡NUEVO SCHEMA! Para asignar repartidor
class AsignarRepartidorInput(BaseModel):
    repartidor_id: int

# ¡NUEVO ENDPOINT! Asignar repartidor a pedido (Admin)
@app.put("/admin/pedidos/{pedido_id}/asignar-repartidor", response_model=dict)
def asignar_repartidor_a_pedido(
    pedido_id: int,
    asignar_input: AsignarRepartidorInput,
    admin_user: UsuarioDB = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Asigna un repartidor a un pedido específico.
    """
    pedido = get_pedido_by_id(db, pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    repartidor = get_usuario_by_id(db, asignar_input.repartidor_id)
    if not repartidor or repartidor.rol != Roles.repartidor:
        raise HTTPException(status_code=404, detail="Repartidor no encontrado o no tiene rol de repartidor")
    
    # Buscar o crear seguimiento
    seguimiento = get_seguimiento_by_pedido_id(db, pedido_id)
    if not seguimiento:
        seguimiento = SeguimientoDB(
            pedido_id=pedido.id,
            estado=EstadoSeguimiento.en_camino,
            hora_estimada_llegada=(datetime.now(timezone.utc) + timedelta(hours=1)).time().isoformat()
        )
        db.add(seguimiento)
    
    # Asignar repartidor
    seguimiento.repartidor_asignado = repartidor.nombre or repartidor.email
    
    # Cambiar estado del pedido a despachado
    pedido.estado = EstadoPedido.despachado
    
    db.commit()
    db.refresh(seguimiento)
    
    print(f"Pedido {pedido_id} asignado a repartidor {repartidor.email}")
    
    return {
        "mensaje": f"Pedido #{pedido_id} asignado a {repartidor.nombre or repartidor.email}",
        "pedido_id": pedido_id,
        "repartidor_id": repartidor.id,
        "repartidor_nombre": repartidor.nombre or repartidor.email
    }

# ¡NUEVO ENDPOINT! Obtener pedidos pendientes de despacho (para repartidores)
@app.get("/pedidos/pendientes/despacho", response_model=List[dict])
def obtener_pedidos_pendientes_despacho(
    current_user: UsuarioDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Obtiene pedidos despachados asignados al repartidor actual.
    Si es admin, muestra todos los pedidos despachados.
    """
    # Si es repartidor, mostrar solo sus pedidos asignados
    if current_user.rol == Roles.repartidor:
        # Buscar pedidos donde el seguimiento tiene asignado a este repartidor
        pedidos = db.query(PedidoDB).filter(
            PedidoDB.estado == EstadoPedido.despachado
        ).all()
        
        result = []
        for pedido in pedidos:
            seguimiento = get_seguimiento_by_pedido_id(db, pedido.id)
            # Solo incluir si está asignado a este repartidor
            if seguimiento and seguimiento.repartidor_asignado:
                repartidor_nombre = current_user.nombre or current_user.email
                if seguimiento.repartidor_asignado == repartidor_nombre:
                    cliente = get_usuario_by_id(db, pedido.usuario_id)
                    result.append({
                        "id": pedido.id,
                        "clientName": cliente.nombre if cliente and cliente.nombre else "Cliente",
                        "address": cliente.direccion if cliente and cliente.direccion else "Sin dirección",
                        "phone": cliente.telefono if cliente and cliente.telefono else "Sin teléfono",
                        "total": pedido.total,
                        "estado": pedido.estado.value,
                        "fecha_creacion": pedido.fecha_creacion.isoformat() if pedido.fecha_creacion else None
                    })
        return result
    
    # Si es admin, mostrar todos los pedidos despachados
    elif current_user.rol == Roles.administrador:
        pedidos = db.query(PedidoDB).filter(
            PedidoDB.estado == EstadoPedido.despachado
        ).all()
        
        result = []
        for pedido in pedidos:
            cliente = get_usuario_by_id(db, pedido.usuario_id)
            seguimiento = get_seguimiento_by_pedido_id(db, pedido.id)
            result.append({
                "id": pedido.id,
                "clientName": cliente.nombre if cliente and cliente.nombre else "Cliente",
                "address": cliente.direccion if cliente and cliente.direccion else "Sin dirección",
                "phone": cliente.telefono if cliente and cliente.telefono else "Sin teléfono",
                "total": pedido.total,
                "estado": pedido.estado.value,
                "repartidor": seguimiento.repartidor_asignado if seguimiento else "Sin asignar",
                "fecha_creacion": pedido.fecha_creacion.isoformat() if pedido.fecha_creacion else None
            })
        return result
    
    # Cliente normal no debería acceder aquí
    else:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver estos pedidos")

# ¡NUEVO ENDPOINT! Marcar pedido como "en camino"
@app.put("/pedidos/{pedido_id}/en-camino", response_model=dict)
def marcar_pedido_en_camino(
    pedido_id: int,
    current_user: UsuarioDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Marca un pedido como despachado/en camino.
    Solo para repartidores o admin.
    """
    if current_user.rol not in [Roles.repartidor, Roles.administrador]:
        raise HTTPException(status_code=403, detail="Solo repartidores o admin pueden marcar pedidos en camino")
    
    pedido = get_pedido_by_id(db, pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    # Cambiar estado a despachado
    pedido.estado = EstadoPedido.despachado
    
    # Crear o actualizar seguimiento
    seguimiento = get_seguimiento_by_pedido_id(db, pedido_id)
    if not seguimiento:
        seguimiento = SeguimientoDB(
            pedido_id=pedido.id,
            estado=EstadoSeguimiento.en_camino,
            hora_estimada_llegada=(datetime.now(timezone.utc) + timedelta(hours=1)).time().isoformat(),
            repartidor_asignado=current_user.nombre or current_user.email
        )
        db.add(seguimiento)
    else:
        seguimiento.estado = EstadoSeguimiento.en_camino
        if not seguimiento.repartidor_asignado:
            seguimiento.repartidor_asignado = current_user.nombre or current_user.email
    
    db.commit()
    db.refresh(pedido)
    
    print(f"Pedido {pedido_id} marcado como EN CAMINO por {current_user.email}")
    
    return {
        "mensaje": f"Pedido #{pedido_id} está en camino",
        "estado": "despachado",
        "pedido_id": pedido_id
    }

# ============================================
# ✅ ENDPOINTS DE PEDIDOS (SIN DUPLICADOS)
# ============================================

# 1. Ruta específica PRIMERO
@app.get("/pedidos/pendientes/despacho", response_model=List[dict])
def obtener_pedidos_pendientes_despacho(
    current_user: UsuarioDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Obtiene pedidos despachados asignados al repartidor actual.
    Si es admin, muestra todos los pedidos despachados.
    """
    # Si es repartidor, mostrar solo sus pedidos asignados
    if current_user.rol == Roles.repartidor:
        # Buscar pedidos donde el seguimiento tiene asignado a este repartidor
        pedidos = db.query(PedidoDB).filter(
            PedidoDB.estado == EstadoPedido.despachado
        ).all()
        
        result = []
        for pedido in pedidos:
            seguimiento = get_seguimiento_by_pedido_id(db, pedido.id)
            # Solo incluir si está asignado a este repartidor
            if seguimiento and seguimiento.repartidor_asignado:
                repartidor_nombre = current_user.nombre or current_user.email
                if seguimiento.repartidor_asignado == repartidor_nombre:
                    cliente = get_usuario_by_id(db, pedido.usuario_id)
                    result.append({
                        "id": pedido.id,
                        "clientName": cliente.nombre if cliente and cliente.nombre else "Cliente",
                        "address": cliente.direccion if cliente and cliente.direccion else "Sin dirección",
                        "phone": cliente.telefono if cliente and cliente.telefono else "Sin teléfono",
                        "total": pedido.total,
                        "estado": pedido.estado.value,
                        "fecha_creacion": pedido.fecha_creacion.isoformat() if pedido.fecha_creacion else None
                    })
        return result
    
    # Si es admin, mostrar todos los pedidos despachados
    elif current_user.rol == Roles.administrador:
        pedidos = db.query(PedidoDB).filter(
            PedidoDB.estado == EstadoPedido.despachado
        ).all()
        
        result = []
        for pedido in pedidos:
            cliente = get_usuario_by_id(db, pedido.usuario_id)
            seguimiento = get_seguimiento_by_pedido_id(db, pedido.id)
            result.append({
                "id": pedido.id,
                "clientName": cliente.nombre if cliente and cliente.nombre else "Cliente",
                "address": cliente.direccion if cliente and cliente.direccion else "Sin dirección",
                "phone": cliente.telefono if cliente and cliente.telefono else "Sin teléfono",
                "total": pedido.total,
                "estado": pedido.estado.value,
                "repartidor": seguimiento.repartidor_asignado if seguimiento else "Sin asignar",
                "fecha_creacion": pedido.fecha_creacion.isoformat() if pedido.fecha_creacion else None
            })
        return result
    
    # Cliente normal no debería acceder aquí
    else:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver estos pedidos")

# 2. Ruta con parámetro
@app.get("/pedidos/{pedido_id}", response_model=dict)
async def obtener_pedido_por_id(pedido_id: int, current_user: UsuarioDB = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Obtener un pedido específico por ID
    """
    pedido = db.query(PedidoDB).filter(
        PedidoDB.id == pedido_id,
        PedidoDB.usuario_id == current_user.id
    ).first()
    
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    return {
        "id": pedido.id,
        "usuario_id": pedido.usuario_id,
        "total": pedido.total,
        "estado": pedido.estado.value if hasattr(pedido.estado, 'value') else pedido.estado,
        "fecha_creacion": pedido.fecha_creacion.isoformat() if pedido.fecha_creacion else None
    }

# 3. Ruta base AL FINAL
@app.get("/pedidos", response_model=List[dict])
async def obtener_pedidos(current_user: UsuarioDB = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Obtener todos los pedidos del usuario actual
    """
    pedidos = db.query(PedidoDB).filter(PedidoDB.usuario_id == current_user.id).all()
    
    result = []
    for pedido in pedidos:
        result.append({
            "id": pedido.id,
            "usuario_id": pedido.usuario_id,
            "total": pedido.total,
            "estado": pedido.estado.value if hasattr(pedido.estado, 'value') else pedido.estado,
            "fecha_creacion": pedido.fecha_creacion.isoformat() if pedido.fecha_creacion else None,
            "clientName": current_user.nombre if current_user.nombre else "Cliente",
            "address": current_user.direccion if current_user.direccion else "Dirección no especificada",
            "phone": current_user.telefono if current_user.telefono else "No especificado"
        })
    
    return result

# ✅ AGREGAR IMPORTS PARA PDF
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from io import BytesIO

# ============================================
# ✅ ENDPOINTS DE DOCUMENTOS TRIBUTARIOS
# ============================================

@app.get("/documentos/descargar-boleta/{pedido_id}")
async def descargar_boleta_pdf(
    pedido_id: int,
    current_user: UsuarioDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Genera y descarga una boleta en PDF para un pedido.
    """
    # Verificar que el pedido pertenece al usuario
    pedido = get_pedido_by_id(db, pedido_id)
    if not pedido or pedido.usuario_id != current_user.id:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    # Buscar documento
    documento = db.query(DocumentoDB).filter(DocumentoDB.pedido_id == pedido_id).first()
    if not documento:
        # Crear documento si no existe
        documento = DocumentoDB(
            pedido_id=pedido_id,
            tipo=TipoDocumento.boleta,
            total=pedido.total
        )
        db.add(documento)
        db.commit()
        db.refresh(documento)
    
    # Generar PDF
    buffer = BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=letter)
    
    # Estilos
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#7B3F00'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    # Contenido
    story = []
    
    # Título
    story.append(Paragraph("CHOCOMANÍA", title_style))
    story.append(Paragraph("Chocolatería Artesanal", styles['Normal']))
    story.append(Spacer(1, 0.3*inch))
    
    # Tipo de documento
    doc_title = "BOLETA ELECTRÓNICA" if documento.tipo == TipoDocumento.boleta else "FACTURA ELECTRÓNICA"
    story.append(Paragraph(doc_title, styles['Heading2']))
    story.append(Paragraph(f"N° B001-{pedido_id:06d}", styles['Normal']))
    story.append(Spacer(1, 0.3*inch))
    
    # Datos del cliente
    data = [
        ['DATOS DEL CLIENTE', ''],
        ['Nombre:', current_user.nombre or current_user.email],
        ['Email:', current_user.email],
        ['Dirección:', current_user.direccion or 'No especificada'],
        ['Teléfono:', current_user.telefono or 'No especificado'],
        ['', ''],
        ['DETALLES DEL PEDIDO', ''],
        ['N° Pedido:', f'#{pedido_id}'],
        ['Fecha:', pedido.fecha_creacion.strftime('%d/%m/%Y %H:%M') if pedido.fecha_creacion else 'N/A'],
        ['Estado:', pedido.estado.value],
    ]
    
    # Si es factura, agregar datos tributarios
    if documento.tipo == TipoDocumento.factura and documento.rut:
        data.insert(2, ['RUT:', documento.rut])
        data.insert(3, ['Razón Social:', documento.razon_social or ''])
    
    # Calcular desglose
    if documento.tipo == TipoDocumento.factura:
        neto = round(pedido.total / 1.19)
        iva = pedido.total - neto
        data.extend([
            ['', ''],
            ['DESGLOSE', ''],
            ['Neto:', f'${neto:,.0f}'],
            ['IVA (19%):', f'${iva:,.0f}'],
            ['TOTAL:', f'${pedido.total:,.0f}'],
        ])
    else:
        data.extend([
            ['', ''],
            ['TOTAL:', f'${pedido.total:,.0f}'],
        ])
    
    # Crear tabla
    table = Table(data, colWidths=[2.5*inch, 4*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7B3F00')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 14),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph("Este documento es válido para todos los efectos tributarios.", styles['Italic']))
    story.append(Paragraph("¡Gracias por tu compra!", styles['Normal']))
    
    # Construir PDF
    pdf.build(story)
    buffer.seek(0)
    
    # Retornar como descarga
    filename = f"Boleta_Chocomania_B{pedido_id:06d}.pdf" if documento.tipo == TipoDocumento.boleta else f"Factura_Chocomania_F{pedido_id:06d}.pdf"
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.post("/documentos/enviar-email", response_model=dict)
async def enviar_documento_por_email(
    pedido_id: int,
    current_user: UsuarioDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Envía la boleta/factura por email al cliente.
    """
    print(f"📧 Enviando documento para pedido ID: {pedido_id} a usuario: {current_user.email}")
    
    # Verificar pedido
    pedido = get_pedido_by_id(db, pedido_id)
    if not pedido:
        print(f"❌ Pedido {pedido_id} no encontrado en BD")
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    if pedido.usuario_id != current_user.id:
        print(f"❌ Pedido {pedido_id} no pertenece al usuario {current_user.id}")
        raise HTTPException(status_code=403, detail="No tienes permiso para este pedido")
    
    # Buscar documento
    documento = db.query(DocumentoDB).filter(DocumentoDB.pedido_id == pedido_id).first()
    if not documento:
        # ✅ Crear documento si no existe
        print(f"⚠️ Documento no encontrado, creando uno nuevo para pedido {pedido_id}")
        documento = DocumentoDB(
            pedido_id=pedido_id,
            tipo=TipoDocumento.boleta,
            total=pedido.total
        )
        db.add(documento)
        db.commit()
        db.refresh(documento)
    
    # ✅ OBTENER NOMBRE CORRECTO DEL CLIENTE
    nombre_cliente = current_user.nombre if current_user.nombre else current_user.email.split('@')[0]
    
    # Preparar email
    doc_tipo = "Boleta" if documento.tipo == TipoDocumento.boleta else "Factura"
    
    cuerpo_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f8f9fa; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; padding: 30px; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #7B3F00; margin-bottom: 10px;">Chocomanía</h1>
                <p style="color: #666;">Chocolatería Artesanal</p>
            </div>
            
            <h2 style="color: #7B3F00;">{doc_tipo} - Chocomanía</h2>
            <hr style="border: 1px solid #ddd;">
            
            <p><strong>Hola {nombre_cliente},</strong></p>
            <p>Adjuntamos tu {doc_tipo} digital correspondiente a la compra realizada.</p>
            
            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                <h3 style="color: #7B3F00; margin-top: 0;">Detalles de la {doc_tipo.lower()}:</h3>
                <ul style="list-style: none; padding: 0;">
                    <li><strong>N° Pedido:</strong> #{pedido_id}</li>
                    <li><strong>Fecha:</strong> {pedido.fecha_creacion.strftime('%d/%m/%Y %H:%M') if pedido.fecha_creacion else 'N/A'}</li>
                    <li><strong>Total:</strong> ${pedido.total:,.0f}</li>
    """
    
    if documento.tipo == TipoDocumento.factura and documento.rut:
        neto = round(pedido.total / 1.19)
        iva = pedido.total - neto
        cuerpo_html += f"""
                    <li><strong>RUT:</strong> {documento.rut}</li>
                    <li><strong>Razón Social:</strong> {documento.razon_social}</li>
                    <li><strong>Neto:</strong> ${neto:,.0f}</li>
                    <li><strong>IVA (19%):</strong> ${iva:,.0f}</li>
        """
    
    cuerpo_html += f"""
                </ul>
            </div>
            
            <div style="background: #e7f3ff; border-left: 4px solid #007bff; padding: 15px, margin: 20px 0;">
                <p style="margin: 0;"><strong>📄 {doc_tipo}_Chocomania_{'B' if documento.tipo == TipoDocumento.boleta else 'F'}{pedido_id:06d}.pdf</strong></p>
                <small style="color: #666;">(Documento tributario electrónico)</small>
            </div>
            
            <p><em>Este documento es válido para todos los efectos tributarios.</em></p>
            
            <p style="margin-top: 30px;"><strong>¡Gracias por tu compra!</strong></p>
            <p style="color: #666;"><em>Equipo Chocomanía</em></p>
            
            <hr style="border: 1px solid #ddd; margin-top: 30px;">
            <p style="text-align: center; color: #999; font-size: 12px;">
                www.chocomania.cl | contacto@chocomania.cl<br>
                Av. Chocolate 123, Santiago
            </p>
        </div>
    </body>
    </html>
    """
    
    # Enviar email
    await enviar_email_async(
        asunto=f"{doc_tipo} Chocomanía - Pedido #{pedido_id}",
        email_destinatario=current_user.email,
        cuerpo_html=cuerpo_html
    )
    
    print(f"✅ Email enviado exitosamente a {current_user.email}")
    
    return {
        "mensaje": f"{doc_tipo} enviada exitosamente",
        "email": current_user.email,
        "pedido_id": pedido_id
    }