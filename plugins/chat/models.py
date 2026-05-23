"""plugins/chat/models.py"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Float
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, timezone

Base = declarative_base()


class ChatSalon(Base):
    __tablename__ = "chat_salons"
    id          = Column(Integer, primary_key=True)
    nom         = Column(String(100), nullable=False)
    description = Column(String(300), nullable=True)
    couleur     = Column(String(10),  default="#003189")
    icone       = Column(String(10),  default="💬")
    type        = Column(String(20),  default="local")   # local | territorial
    cree_par_id = Column(Integer,     nullable=True)
    cree_at     = Column(DateTime,    default=lambda: datetime.now(timezone.utc))
    archive     = Column(Boolean,     default=False)
    ordre       = Column(Integer,     default=100)
    systeme     = Column(Boolean,     default=False)     # salons par défaut non supprimables


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id          = Column(Integer, primary_key=True)
    salon_id    = Column(Integer, nullable=False)
    auteur_id   = Column(Integer, nullable=True)         # None = message système ou inter-GHT
    auteur_nom  = Column(String(200), nullable=False)    # "Directeur de Crise [DEMO]"
    auteur_sigle= Column(String(20),  nullable=True)     # "DEMO"
    contenu     = Column(Text,  nullable=False)
    mentions    = Column(Text,  default="[]")            # JSON list de mentions
    reply_to_id = Column(Integer, nullable=True)         # citation
    horodatage  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    modifie_at  = Column(DateTime, nullable=True)
    supprime    = Column(Boolean, default=False)
    origine     = Column(String(20), default="local")   # local | ght


class ChatPJ(Base):
    __tablename__ = "chat_pj"
    id              = Column(Integer, primary_key=True)
    message_id      = Column(Integer, nullable=False)
    nom_fichier     = Column(String(300), nullable=False)
    taille_octets   = Column(Integer, nullable=False)
    chemin_stockage = Column(String(500), nullable=False)
    uploaded_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ChatPresence(Base):
    __tablename__ = "chat_presence"
    id           = Column(Integer, primary_key=True)
    user_id      = Column(Integer, nullable=False, unique=True)
    display_name = Column(String(200), nullable=False)
    sigle        = Column(String(20),  nullable=True)
    last_seen    = Column(DateTime,    default=lambda: datetime.now(timezone.utc))


class ChatConfig(Base):
    __tablename__ = "chat_config"
    id                    = Column(Integer, primary_key=True, default=1)
    extensions_autorisees = Column(Text, default='[".pdf",".doc",".docx",".xls",".xlsx",".ppt",".pptx",".odt",".ods",".odp",".txt",".csv",".png",".jpg",".jpeg",".gif",".webp",".svg",".mp4",".zip"]')
    taille_max_mo         = Column(Integer, default=10)
    retention_jours       = Column(Integer, default=0)   # 0 = illimité
