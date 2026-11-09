"""Create-only private rehearsal PKI/receiver credentials; no public certificates.

CA signing and backup keys stay in a separate OFFLINE volume, never runtime mounts.
"""
from datetime import datetime,timedelta,timezone
import os
from pathlib import Path
import secrets
from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import ipaddress


def write(path,data):
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(descriptor,'wb') as handle:handle.write(data);handle.flush();os.fsync(handle.fileno())


def provision(roots):
    if set(roots)!={'edge','agent','receiver','offline'}:raise ValueError()
    for root in roots.values():
        root=Path(root)
        if any(p.is_symlink() for p in (root,*root.parents)) or not root.is_dir() or any(root.iterdir()):raise ValueError('Dedicated empty private directories required')
        root.chmod(0o700)
    now=datetime.now(timezone.utc);key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    issuer=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'NextPhase private rehearsal CA')])
    ca=(x509.CertificateBuilder().subject_name(issuer).issuer_name(issuer).public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
        .add_extension(x509.KeyUsage(False,False,False,False,False,True,True,False,False),critical=True).sign(key,hashes.SHA256()))
    leaf_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    leaf=(x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])).issuer_name(issuer)
        .public_key(leaf_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),x509.DNSName('edge'),x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False)
        .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
        .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),critical=False).sign(key,hashes.SHA256()))
    encode=lambda value:value.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    root_pem=ca.public_bytes(serialization.Encoding.PEM);token=secrets.token_urlsafe(48).encode()
    write(roots['offline']/'ca.key',encode(key));write(roots['offline']/'backup.key',Fernet.generate_key())
    write(roots['offline']/'config.key',secrets.token_urlsafe(48).encode())
    write(roots['edge']/'server.key',encode(leaf_key));write(roots['edge']/'server.crt',leaf.public_bytes(serialization.Encoding.PEM))
    for role in ('edge','agent','offline'):write(roots[role]/'root.crt',root_pem)
    for role in ('agent','receiver'):write(roots[role]/'receiver.token',token)
    write(roots['agent']/'config.key',secrets.token_urlsafe(48).encode())
    return {'private_pki_created':True,'publicly_trusted':False,'runtime_ca_signing_key':False,'key_values_printed':False}


def main():
    import json,pwd,sys
    roots={role:Path('/var/nextphase/staging-'+role) for role in ('edge','agent','receiver','offline')}
    if os.geteuid()!=0:raise SystemExit('Use the one-off staging-init service')
    if '--check' in sys.argv:
        account=pwd.getpwnam('nextphase');os.setgroups([]);os.setgid(account.pw_gid);os.setuid(account.pw_uid)
        expected={'edge':['server.key','server.crt','root.crt'],'agent':['receiver.token','root.crt','config.key'],'receiver':['receiver.token'],'offline':['ca.key','backup.key','root.crt','config.key']}
        try:
            for role,names in expected.items():
                for name in names:
                    path=roots[role]/name
                    if not path.is_file() or path.is_symlink() or path.stat().st_mode&0o077:raise ValueError()
            print(json.dumps({'initialized':True}));return
        except Exception:raise SystemExit(1)
    try:
        if any(root.is_symlink() or not root.is_dir() or any(root.iterdir()) for root in roots.values()):raise ValueError()
        account=pwd.getpwnam('nextphase')
        for root in roots.values():root.chmod(0o700);os.chown(root,account.pw_uid,account.pw_gid)
        os.setgroups([]);os.setgid(account.pw_gid);os.setuid(account.pw_uid)
        print(json.dumps(provision(roots)))
    except Exception:raise SystemExit('Staging setup refused; existing credentials/directories preserved') from None

if __name__=='__main__':main()
