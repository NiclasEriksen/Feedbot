from sqlalchemy import Column, Integer, String, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.future import select
from .helpers import program_path


engine = create_async_engine("sqlite+aiosqlite:///db.sql", future=True, echo=True)
Session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()


class StreamDAL():
    def __init__(self, db_session: Session):
        self.db_session = db_session

    async def create_streamlink(self, name: str, author: str, url: str, m3u: str=""):
        sl = StreamLink(name=name, author=author, url=url, m3u=m3u)
        self.db_session.add(sl)
        await self.db_session.flush()

    async def remove_streamlink(self, url: str) -> bool:
        q = await self.db_session.execute(select(StreamLink).filter_by(url=url))
        r = q.scalars().first()
        if r:
            await self.db_session.delete(r)
            await self.db_session.flush()
            return True
        return False

    async def get_all_streams(self) -> {str: [str]}:
        q = await self.db_session.execute(select(StreamLink).order_by(StreamLink.name))
        return q.scalars().all()

    async def update_stream_name(self, stream_id: int, name: str):
        q = update(StreamLink).where(StreamLink.id == stream_id)
        q = q.values(name=name)
        q.execution_options(synchronize_session="fetch")
        await self.db_session.execute(q)


class StreamLink(Base):
    __tablename__ = "streamlinks"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    alt_titles = Column(String)
    url = Column(String)
    m3u = Column(String)
    author = Column(String)




#Base.metadata.create_all(engine)
