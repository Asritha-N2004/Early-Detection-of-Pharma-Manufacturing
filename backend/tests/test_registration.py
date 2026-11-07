import uuid
import pytest
from backend.tests.test_system import client
from backend.app.database import Session,User,Audit
from backend.app.security_models import UserRoleBinding

def test_public_registration_login_and_viewer_permissions(client):
 username='new_'+uuid.uuid4().hex[:10];password='registration-test-password'
 result=client.post('/api/v1/auth/register',json={'username':username,'password':password})
 assert result.status_code==201,result.text
 assert result.json()['role']=='viewer' and result.json()['active']
 assert 'password' not in result.json()
 login=client.post('/api/v1/auth/login',json={'username':username,'password':password})
 assert login.status_code==200
 headers={'Authorization':'Bearer '+login.json()['access_token']}
 assert client.get('/api/v1/processes',headers=headers).status_code==200
 assert client.post('/api/v1/simulation',json={'action':'start'},headers=headers).status_code==403
 assert client.post('/api/v1/users',json={'username':'not_allowed','password':password,'role':'admin'},headers=headers).status_code==403
 assert client.post('/api/v1/auth/register',json={'username':username,'password':password}).status_code==409
 with Session() as db:
  user=db.get(User,username)
  assert user.password!=password and user.role=='viewer'
  assert db.get(UserRoleBinding,username).role_id=='viewer'
  entry=db.query(Audit).filter_by(actor=username,action='user.self_registered').one()
  assert password not in entry.payload

@pytest.mark.parametrize('fields',[
 {'username':'   ','password':'sufficient-test-password'},
 {'username':'valid_name','password':'x9Q!z'},
 {'username':'valid_name','password':'é'*40},
 {'username':'valid_name','password':'sufficient-test-password','role':'admin'},
])
def test_registration_validation_and_no_self_elevation(client,fields):
 result=client.post('/api/v1/auth/register',json=fields)
 assert result.status_code==422
 assert fields['password'] not in result.text

def test_controlled_registration_requires_activation(client,monkeypatch):
 import backend.app.main as main
 monkeypatch.setattr(main,'CONTROLLED',True)
 username='pending_'+uuid.uuid4().hex[:10];password='registration-test-password'
 result=client.post('/api/v1/auth/register',json={'username':username,'password':password})
 assert result.status_code==201 and not result.json()['active']
 assert client.post('/api/v1/auth/login',json={'username':username,'password':password}).status_code==401

@pytest.mark.parametrize('username',['someone@example.com','A User','éclair','x'])
def test_flexible_username_and_eight_character_password(client,username):
 username=username+'_'+uuid.uuid4().hex[:6]
 response=client.post('/api/v1/auth/register',json={'username':'  '+username+'  ','password':'Abcd1234'})
 assert response.status_code==201,response.text
 assert response.json()['username']==username
 assert client.post('/api/v1/auth/login',json={'username':'  '+username+'  ','password':'Abcd1234'}).status_code==200

def test_seven_character_password_rejected(client):
 assert client.post('/api/v1/auth/register',json={'username':'eight_'+uuid.uuid4().hex[:6],'password':'Abcd123'}).status_code==422
