import os  # ← CRÍTICO: DEBE ESTAR AQUÍ
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
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False
    }
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
    activo = Column(Boolean, default=True)
    # ✅ CORREGIDO: Especificar foreign_keys explícitamente
    pedidos = relationship("PedidoDB", back_populates="dueño", foreign_keys="PedidoDB.usuario_id")
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
    repartidor_id = Column(Integer, ForeignKey('usuarios.id'), nullable=True)
    total = Column(Float)
    estado = Column(SAEnum(EstadoPedido), default=EstadoPedido.pendiente_de_pago)
    fecha_creacion = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    fecha_entrega = Column(DateTime(timezone=True), nullable=True)
    # ✅ CORREGIDO: Especificar foreign_keys en ambas relaciones
    dueño = relationship("UsuarioDB", back_populates="pedidos", foreign_keys=[usuario_id])
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

@app.put("/admin/usuarios/{usuario_id}/rol", response_model=UsuarioSchema)
def asignar_rol(usuario_id: int, rol_input: RolUpdate, admin_user: UsuarioDB = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    usuario = get_usuario_by_id(db, usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    usuario.rol = rol_input.nuevo_rol
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

@app.get("/promociones/activas", response_model=List[PromocionSchema])
def leer_promociones_activas(db: Session = Depends(get_db)):
    ahora = datetime.now(timezone.utc)
    promociones = db.query(PromocionDB).filter(
        PromocionDB.activo == True,
        PromocionDB.fecha_termino > ahora
    ).all()
    return promociones


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
        pedido.estado = EstadoPedido.en_preparacion 
        print(f"Pedido {pedido.id} ahora en preparación.")
        
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
        return {"mensaje": "Pago aprobado."}
    else:
        pedido.estado = EstadoPedido.rechazado
        db.commit()
        return {"mensaje": "Transacción no autorizada"}

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

# ¡NUEVO ENDPOINT! (Para enviar Boleta/Factura por email)
@app.post("/pedidos/{pedido_id}/enviar-documento-email", response_model=dict)
async def enviar_documento_por_email(pedido_id: int, current_user: UsuarioDB = Depends(get_current_user), db: Session = Depends(get_db)):
    
    pedido = get_pedido_by_id(db, pedido_id)
    if not pedido or pedido.usuario_id != current_user.id:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
    doc = db.query(DocumentoDB).filter(DocumentoDB.pedido_id == pedido_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado para este pedido")

    email_destinatario = current_user.email # Email por defecto
    asunto = ""
    cuerpo_html = ""

    if doc.tipo == TipoDocumento.factura:
        # Lógica para Factura
        asunto = f"Factura Electrónica por tu Pedido Chocomanía Nº {pedido.id}"
        cuerpo_html = f"""
        <h1>Factura Electrónica Chocomanía</h1>
        <p>Estimado/a {doc.razon_social or current_user.nombre},</p>
        <p>Adjuntamos (simuladamente) la factura electrónica para tu pedido <strong>Nº {pedido.id}</strong>.</p>
        <br>
        <ul>
            <li><strong>RUT:</strong> {doc.rut}</li>
            <li><strong>Razón Social:</strong> {doc.razon_social}</li>
            <li><strong>Total:</strong> ${doc.total}</li>
        </ul>
        <br>
        <p>Este documento es válido para efectos tributarios.</p>
        <p>Equipo Chocomanía</p>
        """
    else:
        # Lógica para Boleta (default)
        asunto = f"Boleta Electrónica por tu Pedido Chocomanía Nº {pedido.id}"
        cuerpo_html = f"""
        <h1>Boleta Electrónica Chocomanía</h1>
        <p>Hola {current_user.nombre or current_user.email},</p>
        <p>Adjuntamos (simuladamente) la boleta electrónica para tu pedido <strong>Nº {pedido.id}</strong>.</p>
        <br>
        <ul>
            <li><strong>Total:</strong> ${doc.total}</li>
            <li><strong>Fecha:</strong> {doc.fecha.strftime('%Y-%m-%d')}</li>
        </ul>
        <br>
        <p>¡Gracias por tu compra!</p>
        <p>Equipo Chocomanía</p>
        """

    # Enviamos el email correspondiente
    await enviar_email_async(
        asunto=asunto,
        email_destinatario=email_destinatario,
        cuerpo_html=cuerpo_html
    )
    
    return {"mensaje": f"Email de {doc.tipo.value} enviado a {email_destinatario}"}


# --- ENDPOINTS DE REPORTES Y DASHBOARD ---
@app.get("/reportes/ventas")
def generar_reporte_ventas(fecha_inicio: date, fecha_fin: date, formato: str = "json", admin_user: UsuarioDB = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    estados_de_venta = [EstadoPedido.pagado, EstadoPedido.en_preparacion, EstadoPedido.despachado, EstadoPedido.entregado]
    pedidos_pagados = db.query(PedidoDB).filter(
        PedidoDB.estado.in_(estados_de_venta),
        func.date(PedidoDB.fecha_creacion) >= fecha_inicio,
        func.date(PedidoDB.fecha_creacion) <= fecha_fin
    ).all()
    if not pedidos_pagados:
        return {"mensaje": "Sin datos disponibles para este período"}
    total_ventas = sum(p.total for p in pedidos_pagados)
    detalle_pedidos = [{"id": p.id, "fecha": p.fecha_creacion.isoformat(), "total": p.total} for p in pedidos_pagados]
    reporte_data = {
        "periodo": f"{fecha_inicio.isoformat()} al {fecha_fin.isoformat()}",
        "total_ventas": total_ventas,
        "cantidad_pedidos": len(pedidos_pagados),
        "detalle": detalle_pedidos
    }
    if formato == "json":
        return reporte_data
    elif formato == "excel" or formato == "pdf":
        output = io.StringIO()
        output.write("id,fecha,total\n")
        for p in detalle_pedidos: output.write(f"{p['id']},{p['fecha']},{p['total']}\n")
        file_content = output.getvalue()
        output.close()
        return StreamingResponse(
            io.BytesIO(file_content.encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=reporte_{fecha_inicio}_a_{fecha_fin}.csv"}
        )
    return HTTPException(status_code=400, detail="Formato no soportado")

@app.get("/dashboard/ventas", response_model=DashboardVentas)
def get_dashboard_ventas(fecha: date, admin_user: UsuarioDB = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    estados_de_venta = [EstadoPedido.pagado, EstadoPedido.en_preparacion, EstadoPedido.despachado, EstadoPedido.entregado]
    pedidos_del_dia = db.query(PedidoDB).filter(
        PedidoDB.estado.in_(estados_de_venta),
        func.date(PedidoDB.fecha_creacion) == fecha
    ).all()
    if not pedidos_del_dia:
        raise HTTPException(status_code=404, detail="No hay ventas para la fecha seleccionada")
    total_acumulado = sum(p.total for p in pedidos_del_dia)
    ticket_promedio = total_acumulado / len(pedidos_del_dia)
    top_productos_simulado = ["Bombones Finos (BBDD)", "Tableta Amarga (BBDD)"]
    ventas_por_hora_simulado = [VentasPorHora(hora=h, total=round(random.uniform(5000, 20000), 0)) for h in range(9, 18)]
    return DashboardVentas(
        total_acumulado=total_acumulado,
        ticket_promedio=ticket_promedio,
        top_productos=top_productos_simulado,
        ventas_por_hora=ventas_por_hora_simulado
    )

@app.get("/dashboard/pedidos-en-curso", response_model=List[DashboardPedidoActivo])
def get_dashboard_pedidos_activos(fecha: date, admin_user: UsuarioDB = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    estados_activos = [EstadoPedido.en_preparacion, EstadoPedido.despachado]
    pedidos_activos = db.query(PedidoDB).filter(
        PedidoDB.estado.in_(estados_activos),
        func.date(PedidoDB.fecha_creacion) == fecha
    ).all()
    dashboard_list = []
    for p in pedidos_activos:
        cliente = get_usuario_by_id(db, p.usuario_id)
        dashboard_list.append(DashboardPedidoActivo(
            id=f"P-{p.id}",
            cliente=cliente.nombre if cliente else "N/A",
            estado=p.estado.value,
            tiempo_estimado=f"{random.randint(5, 20)} min",
            encargado="Laura Pérez (Simulado)"
        ))
    return dashboard_list


# --- ENDPOINTS DE NOTIFICACIONES ---
def enviar_notificacion_interna(db: Session, notificacion_input: EnviarNotificacionInput):
    pedido = get_pedido_by_id(db, notificacion_input.pedido_id)
    if not pedido: return 
    mensaje = f"Tu pedido {pedido.id} "
    hora_estimada_str = None
    if notificacion_input.tipo == TipoNotificacion.pedido_despachado:
        seguimiento = get_seguimiento_by_pedido_id(db, pedido.id)
        if seguimiento and seguimiento.hora_estimada_llegada:
             hora_estimada_str = seguimiento.hora_estimada_llegada
             mensaje += f"ha sido despachado. Llegada estimada: {hora_estimada_str}."
        else:
             mensaje += "ha sido despachado."
    elif notificacion_input.tipo == TipoNotificacion.retraso_entrega:
        mensaje += f"sufrirá un retraso. {notificacion_input.mensaje_opcional or ''}"
    nueva_notificacion_db = NotificacionDB(pedido_id=pedido.id, tipo=notificacion_input.tipo, mensaje=mensaje, hora_estimada=hora_estimada_str)
    db.add(nueva_notificacion_db)
    print(f"NOTIFICACION (Simulada) para Pedido {pedido.id}: {mensaje}")
    return nueva_notificacion_db

@app.post("/notificaciones/enviar", response_model=NotificacionSchema, status_code=201)
def enviar_notificacion_endpoint(notificacion_input: EnviarNotificacionInput, db: Session = Depends(get_db)):
    notificacion = enviar_notificacion_interna(db, notificacion_input)
    if not notificacion:
         raise HTTPException(status_code=404, detail="Pedido no encontrado para notificar")
    db.commit() 
    db.refresh(notificacion)
    return notificacion

@app.put("/notificaciones/pedido/{pedido_id}/actualizar", response_model=NotificacionSchema)
def actualizar_notificacion_endpoint(pedido_id: int, update_input: ActualizarNotificacionInput, db: Session = Depends(get_db)):
    notificaciones_pedido = get_notificacion_by_pedido_id(db, pedido_id)
    if not notificaciones_pedido:
        raise HTTPException(status_code=404, detail="No hay notificaciones para este pedido")
    ultima_notificacion = notificaciones_pedido[-1]
    ultima_notificacion.mensaje = update_input.mensaje_nuevo
    if update_input.nueva_hora_estimada:
        ultima_notificacion.hora_estimada = update_input.nueva_hora_estimada.isoformat()
    db.commit()
    db.refresh(ultima_notificacion)
    print(f"NOTIFICACION ACTUALIZADA (Simulada) Pedido {pedido_id}: {ultima_notificacion.mensaje}")
    return ultima_notificacion


# --- ENDPOINTS DE SEGUIMIENTO ---
@app.get("/seguimiento/{pedido_id}", response_model=SeguimientoSchema)
def obtener_seguimiento_cliente(pedido_id: int, current_user: UsuarioDB = Depends(get_current_user), db: Session = Depends(get_db)):
    pedido = get_pedido_by_id(db, pedido_id)
    if not pedido or pedido.usuario_id != current_user.id:
        raise HTTPException(status_code=404, detail="Pedido no encontrado o no autorizado")
    seguimiento = get_seguimiento_by_pedido_id(db, pedido.id)
    if not seguimiento:
         raise HTTPException(status_code=404, detail="Seguimiento no iniciado para este pedido")
    if seguimiento.estado == EstadoSeguimiento.en_camino:
        seguimiento.lat = round(random.uniform(-33.4, -33.5), 6)
        seguimiento.lng = round(random.uniform(-70.6, -70.7), 6)
        db.commit()
        db.refresh(seguimiento)
    return seguimiento

@app.put("/seguimiento/{pedido_id}/entregar", response_model=SeguimientoSchema)
def confirmar_entrega_repartidor(pedido_id: int, entrega_input: ConfirmarEntregaInput, repartidor: UsuarioDB = Depends(get_current_repartidor_user), db: Session = Depends(get_db)):
    seguimiento = get_seguimiento_by_pedido_id(db, pedido_id)
    if not seguimiento:
        raise HTTPException(status_code=404, detail="Seguimiento no encontrado")
    if seguimiento.estado == EstadoSeguimiento.entregado:
        raise HTTPException(status_code=400, detail="El pedido ya fue marcado como entregado")
    
    seguimiento.estado = EstadoSeguimiento.entregado
    seguimiento.lat = None
    seguimiento.lng = None
    
    pedido = get_pedido_by_id(db, pedido_id)
    if pedido:
        pedido.estado = EstadoPedido.entregado
        print(f"Pedido {pedido_id} marcado como Entregado por Repartidor {repartidor.email}.")
    
    db.commit()
    db.refresh(seguimiento)
    return seguimiento

# ✅ NUEVO: Endpoint para obtener pedidos del usuario actual
@app.get("/pedidos/mis-pedidos", response_model=List[dict])
async def mis_pedidos(
    current_user: UsuarioDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Obtener todos los pedidos del usuario actual
    """
    pedidos = db.query(PedidoDB).filter(PedidoDB.usuario_id == current_user.id).all()
    
    return [
        {
            "id": p.id,
            "total": p.total,
            "estado": p.estado.value,
            "fecha_creacion": p.fecha_creacion.isoformat() if p.fecha_creacion else None,
            "repartidor_id": p.repartidor_id
        }
        for p in pedidos
    ]

# ✅ NUEVO: Endpoint para obtener un pedido específico
@app.get("/pedidos/{pedido_id}", response_model=dict)
async def obtener_pedido(
    pedido_id: int,
    current_user: UsuarioDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Obtener detalles de un pedido específico
    """
    pedido = db.query(PedidoDB).filter(PedidoDB.id == pedido_id).first()
    
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    # Verificar que el usuario sea el dueño del pedido o sea admin/repartidor
    if pedido.usuario_id != current_user.id and current_user.rol not in [Roles.administrador, Roles.repartidor]:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver este pedido")
    
    return {
        "id": pedido.id,
        "usuario_id": pedido.usuario_id,
        "repartidor_id": pedido.repartidor_id,
        "total": pedido.total,
        "estado": pedido.estado.value,
        "fecha_creacion": pedido.fecha_creacion.isoformat() if pedido.fecha_creacion else None,
        "fecha_entrega": pedido.fecha_entrega.isoformat() if pedido.fecha_entrega else None
    }

# ✅ NUEVO: Endpoint para marcar pedido como pagado
@app.put("/pedidos/{pedido_id}/pagar", response_model=dict)
async def marcar_pedido_pagado(
    pedido_id: int,
    current_user: UsuarioDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Marcar un pedido como pagado (después de procesar el pago)
    """
    pedido = db.query(PedidoDB).filter(PedidoDB.id == pedido_id).first()
    
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    # Verificar que el usuario sea el dueño del pedido
    if pedido.usuario_id != current_user.id:
        raise HTTPException(status_code=403, detail="No tienes permiso para modificar este pedido")
    
    # Cambiar estado a pagado
    pedido.estado = EstadoPedido.pagado
    db.commit()
    db.refresh(pedido)
    
    return {
        "ok": True,
        "pedido_id": pedido.id,
        "nuevo_estado": pedido.estado.value,
        "mensaje": f"Pedido {pedido.id} marcado como pagado"
    }

# ✅ NUEVO: Endpoint para enviar boleta/factura por email
@app.post("/documentos/enviar-email")
async def enviar_documento_email(
    pedido_data: dict,
    current_user: UsuarioDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Enviar boleta o factura por email al usuario
    """
    pedido_id = pedido_data.get("pedido_id")
    
    if not pedido_id:
        raise HTTPException(status_code=400, detail="pedido_id es requerido")
    
    pedido = db.query(PedidoDB).filter(PedidoDB.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    # Verificar que el usuario sea el dueño del pedido
    if pedido.usuario_id != current_user.id:
        raise HTTPException(status_code=403, detail="No tienes permiso para este pedido")
    
    try:
        # Obtener datos del usuario
        usuario = current_user
        
        # Generar contenido del email
        fecha = pedido.fecha_creacion.strftime("%d-%m-%Y") if pedido.fecha_creacion else "N/A"
        total = f"${pedido.total:,.0f}".replace(",", ".")
        
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; background-color: #f8f9fa; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
                    <!-- Header -->
                    <div style="background: linear-gradient(135deg, #7B3F00, #A0522D); color: white; padding: 20px; text-align: center;">
                        <h1 style="margin: 0; font-size: 1.8rem;">CHOCOMANÍA</h1>
                        <p style="margin: 5px 0 0 0;">Chocolatería Artesanal</p>
                    </div>
                    
                    <!-- Contenido -->
                    <div style="padding: 30px;">
                        <h2 style="color: #7B3F00; margin-bottom: 20px;">¡Hola {usuario.nombre or usuario.email}!</h2>
                        
                        <p style="color: #333; line-height: 1.6;">
                            Adjuntamos tu <strong>boleta digital</strong> correspondiente a la compra realizada en Chocomanía.
                        </p>
                        
                        <!-- Detalles del pedido -->
                        <div style="background: #f8f9fa; border-left: 4px solid #FFB300; padding: 15px; margin: 20px 0; border-radius: 5px;">
                            <h4 style="color: #7B3F00; margin-top: 0;">Detalles de tu Pedido:</h4>
                            <p style="margin: 5px 0;"><strong>N° Pedido:</strong> #{pedido.id}</p>
                            <p style="margin: 5px 0;"><strong>Fecha:</strong> {fecha}</p>
                            <p style="margin: 5px 0;"><strong>Total:</strong> {total}</p>
                            <p style="margin: 5px 0;"><strong>Estado:</strong> <span style="background: #d4edda; color: #155724; padding: 3px 8px; border-radius: 12px; font-size: 0.9rem;">PAGADO</span></p>
                        </div>
                        
                        <p style="color: #666; font-size: 0.9rem;">
                            Este documento es válido para todos los efectos tributarios. 
                            <br>¡Gracias por tu compra!
                        </p>
                        
                        <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd;">
                            <p style="color: #666; font-size: 0.85rem; margin: 5px 0;">
                                Equipo de Chocomanía<br>
                                contacto@chocomania.cl | +56 2 2123 4567
                            </p>
                        </div>
                    </div>
                </div>
            </body>
        </html>
        """
        
        # Crear mensaje de email
        message = MessageSchema(
            subject="🍫 Tu Boleta Chocomanía - Pedido #" + str(pedido.id),
            recipients=[usuario.email],
            html=html_content
        )
        
        # Enviar email
        fm = FastMail(conf)
        await fm.send_message(message)
        
        print(f"✅ Email enviado a {usuario.email}")
        
        return {
            "ok": True,
            "mensaje": f"Boleta enviada a {usuario.email}",
            "email": usuario.email
        }
    
    except Exception as e:
        print(f"❌ Error enviando email: {e}")
        return {
            "ok": False,
            "mensaje": "Error al enviar email. Intenta más tarde.",
            "error": str(e)
        }

# ✅ NUEVO: Endpoint para descargar boleta en PDF
@app.get("/documentos/descargar-boleta/{pedido_id}")
async def descargar_boleta(
    pedido_id: int,
    current_user: UsuarioDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Descargar boleta en formato PDF
    """
    pedido = db.query(PedidoDB).filter(PedidoDB.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    # Verificar que el usuario sea el dueño del pedido
    if pedido.usuario_id != current_user.id:
        raise HTTPException(status_code=403, detail="No tienes permiso para este pedido")
    
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from io import BytesIO
        
        # Crear PDF en memoria
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=letter)
        
        # Estilos
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#7B3F00'),
            spaceAfter=12,
            alignment=1  # CENTER
        )
        
        # Contenido del PDF
        story = []
        
        # Título
        story.append(Paragraph("CHOCOMANÍA", title_style))
        story.append(Paragraph("Chocolatería Artesanal", styles['Heading3']))
        story.append(Spacer(1, 0.3*inch))
        
        # Datos del pedido
        data = [
            ['BOLETA DE VENTA', ''],
            ['N° Pedido:', f"#{pedido.id}"],
            ['Fecha:', pedido.fecha_creacion.strftime("%d-%m-%Y") if pedido.fecha_creacion else "N/A"],
            ['Cliente:', current_user.nombre or current_user.email],
            ['Email:', current_user.email],
            ['Dirección:', current_user.direccion or "No registrada"],
        ]
        
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7B3F00')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey)
        ]))
        
        story.append(table)
        story.append(Spacer(1, 0.3*inch))
        
        # Total
        total_data = [
            ['TOTAL A PAGAR:', f"${pedido.total:,.0f}"],
        ]
        total_table = Table(total_data)
        total_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#d4edda')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#155724')),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('PADDING', (0, 0), (-1, -1), 10),
        ]))
        
        story.append(total_table)
        story.append(Spacer(1, 0.5*inch))
        
        # Pie
        story.append(Paragraph(
            "Este documento es válido para todos los efectos tributarios.<br/>"
            "Gracias por tu compra en Chocomanía",
            styles['Normal']
        ))
        
        # Generar PDF
        doc.build(story)
        pdf_buffer.seek(0)
        
        # Retornar como descarga
        return StreamingResponse(
            iter([pdf_buffer.getvalue()]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=Boleta_Chocomania_B{pedido.id:06d}.pdf"}
        )
    
    except Exception as e:
        print(f"Error generando PDF: {e}")
        raise HTTPException(status_code=500, detail="Error al generar PDF")

# ✅ VERIFICAR: Endpoint para crear pedido desde carrito
@app.post("/pedidos/crear-pago-desde-carrito", response_model=dict)
async def crear_pedido_desde_carrito(
    current_user: UsuarioDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Crear un nuevo pedido a partir del carrito del usuario actual
    """
    try:
        print(f"🔵 Creando pedido para usuario: {current_user.id}")
        
        # Obtener carrito del usuario
        carrito = db.query(CarritoDB).filter(CarritoDB.usuario_id == current_user.id).first()
        
        if not carrito:
            print(f"❌ No hay carrito para usuario {current_user.id}")
            raise HTTPException(status_code=400, detail="El carrito está vacío")
        
        # Obtener items del carrito
        carrito_items = db.query(CarritoItemDB).filter(CarritoItemDB.carrito_id == carrito.id).all()
        
        print(f"📦 Items en carrito: {len(carrito_items)}")
        
        if not carrito_items or len(carrito_items) == 0:
            raise HTTPException(status_code=400, detail="No hay productos en el carrito")
        
        # Calcular total
        total = 0
        for item in carrito_items:
            if item.producto:
                total += item.cantidad * item.producto.precio
                print(f"  - {item.producto.nombre}: {item.cantidad} x ${item.producto.precio}")
        
        print(f"💰 Total calculado: ${total}")
        
        if total <= 0:
            raise HTTPException(status_code=400, detail="El total debe ser mayor a 0")
        
        # Crear pedido
        nuevo_pedido = PedidoDB(
            usuario_id=current_user.id,
            total=total,
            estado=EstadoPedido.pendiente_de_pago,
            fecha_creacion=datetime.now(timezone.utc)
        )
        
        db.add(nuevo_pedido)
        db.flush()  # Obtener el ID del pedido antes de commit
        
        print(f"✅ Pedido creado con ID: {nuevo_pedido.id}")
        
        # Asociar productos al pedido
        for item in carrito_items:
            db.execute(
                pedido_items_tabla.insert().values(
                    pedido_id=nuevo_pedido.id,
                    producto_id=item.producto_id,
                    cantidad=item.cantidad,
                    precio_en_el_momento=item.producto.precio if item.producto else 0
                )
            )
        
        # Vaciar carrito después de crear el pedido
        db.query(CarritoItemDB).filter(CarritoItemDB.carrito_id == carrito.id).delete()
        
        db.commit()
        db.refresh(nuevo_pedido)
        
        print(f"✅ Pedido #{nuevo_pedido.id} creado exitosamente - Total: ${nuevo_pedido.total}")
        
        return {
            "ok": True,
            "pedido_id": nuevo_pedido.id,
            "total": nuevo_pedido.total,
            "estado": nuevo_pedido.estado.value,
            "mensaje": f"Pedido #{nuevo_pedido.id} creado exitosamente"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ Error creando pedido: {e}")
        raise HTTPException(status_code=500, detail=f"Error al crear pedido: {str(e)}")