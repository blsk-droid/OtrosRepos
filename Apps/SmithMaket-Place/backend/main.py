import os
import sys
import threading
import time
import uvicorn
import webview
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from db.models import Base, Book
from engine.importer import parse_docx
from engine.pagination import paginate_book
from engine.exporter import export_pdf, export_docx

# 1. Database URL configuration
# Decide DB host depending on container environment (postgres_db inside docker, localhost outside docker)
IS_DOCKER = os.environ.get("IS_DOCKER", "false").lower() == "true"
db_host = "postgres_db" if IS_DOCKER else "localhost"
DB_URL = f"postgresql://admin_antigravity:TuPasswordSeguroAqui@{db_host}:5432/wedding_antigravity_dev"

# Database Engine Setup
engine = None
SessionLocal = None

try:
    engine = create_engine(DB_URL, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    # Test connection
    with engine.connect() as conn:
        pass
except Exception as e:
    print(f"PostgreSQL connection failed: {e}. Falling back to SQLite local database.")
    # Local SQLite fallback for resiliency
    sqlite_path = "/app/datos/local_sqlite.db" if IS_DOCKER else "F:\\Aplicaciones\\MaketNovels\\datos\\local_sqlite.db"
    os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
    DB_URL = f"sqlite:///{sqlite_path}"
    engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 2. FastAPI Application Configuration
app = FastAPI(
    title="Antigravity 2.0 API",
    description="Backend de maquetación profesional para Amazon KDP",
    version="2.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Schemas for validation
class BookUpdate(BaseModel):
    title: str
    author: Optional[str] = None
    docx_filename: Optional[str] = None
    kdp_width_inches: float
    kdp_height_inches: float
    margin_inner_inches: float
    margin_outer_inches: float
    margin_top_inches: float
    margin_bottom_inches: float
    font_family: str
    font_size_pt: float
    line_height_relative: float
    letter_spacing_pt: float
    widow_orphan_control: bool
    content_blocks: List[Dict[str, Any]]
    style_mappings: Dict[str, str]
    chapter_definitions: Dict[str, Any]

# API Endpoints
@app.get("/")
def read_root():
    return {"status": "online", "project": "Antigravity 2.0", "environment": "Docker" if IS_DOCKER else "Local"}

@app.get("/api/health")
def health_check():
    return {"database": "connected", "weasyprint": "ready"}

@app.post("/api/import")
async def import_document(file: UploadFile = File(...)):
    """
    Accepts DOCX document file upload, parses content block structures, and performs
    initial heuristic analysis for chapter headers.
    """
    temp_dir = "/app/datos/temp" if IS_DOCKER else "F:\\Aplicaciones\\MaketNovels\\datos\\temp"
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, file.filename)
    
    try:
        content = await file.read()
        with open(temp_path, "wb") as buffer:
            buffer.write(content)
        
        parsed_data = parse_docx(temp_path)
        parsed_data["docx_filename"] = file.filename
        return parsed_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse DOCX: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.post("/api/paginate")
def paginate_document(book_data: Dict[str, Any]):
    """
    Executes Pillow font metrics measurement calculations and packages text into pagination spreads.
    """
    try:
        pages = paginate_book(book_data)
        return {"pages": pages, "total_pages": len(pages)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Typesetting pagination failure: {str(e)}")

@app.get("/api/books")
def list_books(db: Session = Depends(get_db)):
    """
    Fetches the list of saved book layouts from the database.
    """
    books = db.query(Book).order_by(Book.updated_at.desc()).all()
    return [b.to_dict() for b in books]

@app.post("/api/books")
def create_book(book_update: BookUpdate, db: Session = Depends(get_db)):
    """
    Creates and saves a new book project.
    """
    db_book = Book(**book_update.model_dump())
    db.add(db_book)
    db.commit()
    db.refresh(db_book)
    return db_book.to_dict()

@app.get("/api/books/{book_id}")
def get_book(book_id: str, db: Session = Depends(get_db)):
    """
    Retrieves project details for a specific book layout.
    """
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book project not found")
    return book.to_dict()

@app.put("/api/books/{book_id}")
def update_book(book_id: str, book_update: BookUpdate, db: Session = Depends(get_db)):
    """
    Updates layout specifications or styling tokens for a book project.
    """
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book project not found")
        
    for key, value in book_update.model_dump().items():
        setattr(book, key, value)
        
    db.commit()
    db.refresh(book)
    return book.to_dict()

@app.post("/api/export/pdf")
def export_book_pdf(book_data: Dict[str, Any]):
    """
    Triggers WeasyPrint compiler to build printable CMYK PDF.
    """
    try:
        pages = paginate_book(book_data)
        temp_dir = "/app/datos/temp" if IS_DOCKER else "F:\\Aplicaciones\\MaketNovels\\datos\\temp"
        os.makedirs(temp_dir, exist_ok=True)
        temp_pdf = os.path.join(temp_dir, f"export_{time.time_ns()}.pdf")
        
        export_pdf(book_data, pages, temp_pdf)
        return FileResponse(temp_pdf, media_type="application/pdf", filename=f"{book_data.get('title', 'book')}.pdf")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation export failed: {str(e)}")

@app.post("/api/export/docx")
def export_book_docx(book_data: Dict[str, Any]):
    """
    Triggers word-processing layout exporter to write symmetrical DOCX.
    """
    try:
        pages = paginate_book(book_data)
        temp_dir = "/app/datos/temp" if IS_DOCKER else "F:\\Aplicaciones\\MaketNovels\\datos\\temp"
        os.makedirs(temp_dir, exist_ok=True)
        temp_docx = os.path.join(temp_dir, f"export_{time.time_ns()}.docx")
        
        export_docx(book_data, pages, temp_docx)
        return FileResponse(temp_docx, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=f"{book_data.get('title', 'book')}.docx")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DOCX layout export failed: {str(e)}")

# Mount static frontend production folder if available
frontend_dist_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frontend", "dist", "frontend", "browser")
)
if os.path.exists(frontend_dist_path):
    app.mount("/", StaticFiles(directory=frontend_dist_path, html=True), name="static")

# 3. Desktop Native API Wrapper Bridge (PyWebView Interface)
class NativeApi:
    def get_system_fonts(self) -> List[str]:
        system_root = os.environ.get("SystemRoot", "C:\\Windows")
        fonts_dir = os.path.join(system_root, "Fonts")
        
        font_map = {
            "gara.ttf": "Garamond",
            "georgia.ttf": "Georgia",
            "times.ttf": "Times New Roman",
            "baskvill.ttf": "Baskerville",
            "bkant.ttf": "Book Antiqua",
            "pala.ttf": "Palatino",
        }
        
        available = []
        if os.path.exists(fonts_dir):
            for file in os.listdir(fonts_dir):
                normalized = file.lower()
                if normalized in font_map:
                    available.append(font_map[normalized])
        return list(set(available)) if available else ["Times New Roman", "Georgia"]

    def select_file(self) -> Optional[str]:
        window = webview.active_window()
        if window:
            result = window.create_file_dialog(
                webview.OPEN_DIALOG, 
                allow_multiple=False, 
                file_types=('Word Documents (*.docx)',)
            )
            return result[0] if result else None
        return None

def start_fastapi():
    init_db()
    # Inside docker we run on 0.0.0.0 so host port binding works, on local windows we run on 127.0.0.1
    host_ip = "0.0.0.0" if IS_DOCKER else "127.0.0.1"
    uvicorn.run("main:app", host=host_ip, port=8000, reload=False)

if __name__ == "__main__":
    is_dev = "--dev" in sys.argv or not IS_DOCKER
    
    if IS_DOCKER:
        print("\n" + "="*60)
        print(" ARRANQUE EXCELENTE: Modo Docker Detectado")
        print(" Servidor API activo y escuchando en http://0.0.0.0:8000")
        print(" WeasyPrint ejecutándose de forma nativa en Linux.")
        print("="*60 + "\n")
        
        start_fastapi()
    else:
        # Start FastAPI in a background daemon thread
        api_thread = threading.Thread(target=start_fastapi, daemon=True)
        api_thread.start()
        time.sleep(1.5)
        
        print("\n" + "="*60)
        print(" ARRANQUE: Modo Escritorio Windows Detectado")
        print(" Levantando ventana nativa de PyWebView...")
        print("="*60 + "\n")
        
        # Configure PyWebView to load local frontend or build directory
        start_url = "http://localhost:4200" if is_dev else "http://127.0.0.1:8000"
        
        api = NativeApi()
        webview.create_window(
            'Antigravity 2.0',
            url=start_url,
            js_api=api,
            width=1280,
            height=800,
            min_size=(1024, 768)
        )
        webview.start(debug=is_dev)