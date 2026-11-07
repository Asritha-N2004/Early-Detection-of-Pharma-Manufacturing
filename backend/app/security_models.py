from sqlalchemy import String,Boolean,ForeignKey
from sqlalchemy.orm import Mapped,mapped_column
from .database import Base

class UserSession(Base):
    __tablename__='user_sessions'
    id:Mapped[str]=mapped_column(String,primary_key=True)
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    created:Mapped[str]=mapped_column(String)
    expires:Mapped[str]=mapped_column(String,index=True)
    revoked:Mapped[bool]=mapped_column(Boolean,default=False)
class UserRoleBinding(Base):
    __tablename__='user_roles'
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id'),primary_key=True)
    role_id:Mapped[str]=mapped_column(ForeignKey('roles.id'))
