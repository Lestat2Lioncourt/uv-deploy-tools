#!/usr/bin/env python
"""
UV Deploy Tools - Outil de déploiement automatisé pour projets Python sur serveurs Windows et Linux
"""

import sys
import os
from pathlib import Path
import shutil
import zipfile
import tarfile
import tempfile
from getpass import getpass
import subprocess
import urllib.request
from datetime import datetime
import click
import yaml
import paramiko
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, DownloadColumn, TransferSpeedColumn
from rich.table import Table

console = Console()

class OrbitDeployer:
    def __init__(self, project_name, server, password=None):
        self.project_name = project_name
        self.project_path = Path("..") / project_name
        self.server_config = self.load_server_config(server)
        self.password = password
        self.ssh = None
        self.sftp = None
        
        # Vérifier que le projet existe
        if not self.project_path.exists():
            console.print(f"[red] Projet '{project_name}' introuvable dans {self.project_path.absolute()}[/red]")
            sys.exit(1)
            
    def load_server_config(self, server_name):
        config_file = Path("configs/servers.yaml")
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        if server_name not in config['servers']:
            console.print(f"[red] Serveur '{server_name}' non trouvé dans la configuration[/red]")
            sys.exit(1)
            
        server_config = config['servers'][server_name]
        server_config['defaults'] = config.get('defaults', {})
        return server_config
    
    def get_project_version(self):
        """Obtenir la version du projet depuis pyproject.toml"""
        pyproject_path = self.project_path / "pyproject.toml"
        if pyproject_path.exists():
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib
                
            with open(pyproject_path, 'rb') as f:
                data = tomllib.load(f)
                return data.get('project', {}).get('version', '0.1.0')
        return '0.1.0'
    
    def connect(self):
        """Établir la connexion SSH avec support du port personnalisé"""
        console.print("[cyan] Connexion au serveur...[/cyan]")
        
        if not self.password:
            self.password = getpass(f"Mot de passe pour {self.server_config['user']}@{self.server_config['host']}: ")
        
        # Récupérer le port (22 par défaut)
        port = self.server_config.get('port', 22)
        
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(
                self.server_config['host'],
                port=port,
                username=self.server_config['user'],
                password=self.password
            )
            self.sftp = self.ssh.open_sftp()
            console.print(f"[green] Connecté avec succès (port {port})[/green]")
            return True
        except Exception as e:
            console.print(f"[red] Erreur de connexion: {e}[/red]")
            return False
    
    def get_python_version(self):
        """Obtenir la version Python du projet"""
        python_version_file = self.project_path / ".python-version"
        if python_version_file.exists():
            return python_version_file.read_text().strip()
        return self.server_config['defaults'].get('python_version', '3.12')
    
    def download_uv(self, deploy_dir):
        """Télécharger UV selon l'OS cible"""
        target_os = self.server_config.get('os', 'windows').lower()
        
        if target_os == 'windows':
            uv_filename = 'uv.exe'
            uv_url = self.server_config['defaults']['uv_download_url']
        else:
            uv_filename = 'uv'
            # URL pour Linux x64
            uv_url = 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-unknown-linux-gnu.tar.gz'
        
        uv_cache = Path(f"cache/{uv_filename}_{target_os}")
        
        if not uv_cache.exists():
            console.print(f"[cyan] Téléchargement d'UV pour {target_os}...[/cyan]")
            uv_cache.parent.mkdir(exist_ok=True)
            
            if target_os == 'windows':
                # Télécharger le ZIP pour Windows
                zip_path = Path(f"cache/uv_{target_os}.zip")
                with Progress() as progress:
                    task = progress.add_task("[cyan]Téléchargement...", total=100)
                    urllib.request.urlretrieve(uv_url, zip_path, 
                        lambda b, bs, ts: progress.update(task, completed=(b*bs/ts)*100) if ts > 0 else None)
                
                # Extraire
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extract('uv.exe', 'cache')
                zip_path.unlink()
                # Renommer pour avoir le suffixe OS
                Path('cache/uv.exe').rename(uv_cache)
            else:
                # Télécharger tar.gz pour Linux
                tar_path = Path(f"cache/uv_{target_os}.tar.gz")
                with Progress() as progress:
                    task = progress.add_task("[cyan]Téléchargement...", total=100)
                    urllib.request.urlretrieve(uv_url, tar_path,
                        lambda b, bs, ts: progress.update(task, completed=(b*bs/ts)*100) if ts > 0 else None)
                
                # Extraire - CORRECTION ICI
                import tarfile
                with tarfile.open(tar_path, 'r:gz') as tf:
                    # Extraire tous les fichiers
                    tf.extractall('cache/temp_uv')
                
                # Trouver le fichier uv
                temp_dir = Path('cache/temp_uv')
                uv_file = None
                for file in temp_dir.rglob('uv'):
                    if file.is_file():
                        uv_file = file
                        break
                
                if uv_file:
                    uv_file.rename(uv_cache)
                    shutil.rmtree(temp_dir, ignore_errors=True)
                else:
                    console.print("[red]Erreur: fichier uv non trouvé dans l'archive[/red]")
                    return False
                    
                tar_path.unlink()
            
            console.print("[green] UV téléchargé[/green]")
        
        # Copier dans le package
        shutil.copy2(uv_cache, deploy_dir / uv_filename)
        
        # Rendre exécutable si Linux
        if target_os == 'linux':
            (deploy_dir / uv_filename).chmod(0o755)
        
        return True

    def find_best_python_version(self, requested_version, target_os):
        """Trouver la meilleure version Python disponible"""
        import re
        
        # Parser la version demandée
        match = re.match(r'(\d+)\.(\d+)(?:\.(\d+))?', requested_version)
        if not match:
            return requested_version, requested_version
        
        major = int(match.group(1))
        minor = int(match.group(2))
        
        # Pour Linux, versions standalone disponibles avec leurs dates de build
        if target_os == 'linux':
            # Format: 'version courte': ('version complète', 'date de build')
            available_versions = {
                '3.13': ('3.13.0', '20241016'),
                '3.12': ('3.12.7', '20241016'),
                '3.11': ('3.11.10', '20240909'),
                '3.10': ('3.10.15', '20240909'),
            }
        else:
            # Pour Windows, chercher dans le cache UV local
            base_paths = [
                Path(f"C:/Users/{os.environ.get('USERNAME', 'user')}/AppData/Roaming/uv/python"),
            ]
            
            available_versions = {}
            for base_path in base_paths:
                if base_path.exists():
                    for folder in base_path.glob("cpython-*"):
                        version_match = re.search(r'cpython-(\d+\.\d+(?:\.\d+)?)', folder.name)
                        if version_match:
                            ver = version_match.group(1)
                            short_ver = '.'.join(ver.split('.')[:2])
                            available_versions[short_ver] = (ver, None)
        
        # Chercher la version exacte ou la plus proche inférieure
        requested_short = f"{major}.{minor}"
        
        if requested_short in available_versions:
            console.print(f"[green] Version {requested_short} disponible[/green]")
            return requested_short, available_versions[requested_short]
        
        # Chercher la version inférieure la plus proche
        fallback_version = None
        fallback_info = None
        
        for v_short, v_info in sorted(available_versions.items(), reverse=True):
            v_major, v_minor = map(int, v_short.split('.'))
            if v_major < major or (v_major == major and v_minor < minor):
                fallback_version = v_short
                fallback_info = v_info
                break
        
        if fallback_version:
            console.print(f"[yellow] Version {requested_version} non disponible[/yellow]")
            console.print(f"[cyan] Utilisation de la version {fallback_version} (plus proche inférieure)[/cyan]")
            
            # Sauvegarder la préférence pour réessayer plus tard
            fallback_file = Path(f"cache/.python_fallback_{self.project_name}")
            fallback_file.write_text(f"{requested_version}|{fallback_version}|{datetime.now().isoformat()}")
            
            return fallback_version, fallback_info
        
        console.print(f"[red] Aucune version Python compatible trouvée[/red]")
        return None, None

    def copy_python(self, deploy_dir, python_version):
        """Copier Python portable selon l'OS cible avec fallback intelligent"""
        target_os = self.server_config.get('os', 'windows').lower()
        
        # Vérifier si on peut utiliser la version originale maintenant
        fallback_file = Path(f"cache/.python_fallback_{self.project_name}")
        if fallback_file.exists():
            original, used, timestamp = fallback_file.read_text().split('|')
            console.print(f"[dim]Note: Version {original} demandée précédemment, {used} utilisée[/dim]")
            # Réessayer avec la version originale
            python_version = original
        
        # Trouver la meilleure version disponible
        best_version, version_info = self.find_best_python_version(python_version, target_os)
        
        if not best_version:
            return False
        
        if target_os == 'windows':
            # Logique Windows existante
            base_paths = [
                Path(f"C:/Users/{os.environ.get('USERNAME', 'user')}/AppData/Roaming/uv/python"),
                Path(f"C:/Users/{os.environ.get('USERNAME', 'user')}/.local/share/uv/python"),
            ]
            
            pattern = f"cpython-{best_version}*-windows-x86_64-none"
            
            python_path = None
            for base_path in base_paths:
                if base_path.exists():
                    found = list(base_path.glob(pattern))
                    if found:
                        python_path = found[0]
                        break
            
            if not python_path:
                console.print(f"[red] Python {best_version} pour Windows non trouvé[/red]")
                return False
                
        else:  # Linux
            # Extraire la version complète et la date de build
            full_version, build_date = version_info
            
            python_cache = Path(f"cache/python-{best_version}-linux")
            
            if not python_cache.exists():
                # URL avec la bonne date de build
                base_url = f"https://github.com/indygreg/python-build-standalone/releases/download/{build_date}"
                python_url = f"{base_url}/cpython-{full_version}+{build_date}-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
                
                console.print(f"[cyan] Téléchargement de Python {best_version} pour Linux...[/cyan]")
                console.print(f"[dim]URL: {python_url}[/dim]")
                tar_path = Path(f"cache/python-{best_version}-linux.tar.gz")
                
                try:
                    with Progress() as progress:
                        task = progress.add_task(f"[cyan]Téléchargement Python {best_version}...", total=100)
                        urllib.request.urlretrieve(python_url, tar_path,
                            lambda b, bs, ts: progress.update(task, completed=(b*bs/ts)*100) if ts > 0 else None)
                    
                    # Extraire
                    console.print("[cyan]Extraction de Python...[/cyan]")
                    import tarfile
                    with tarfile.open(tar_path, 'r:gz') as tf:
                        tf.extractall(python_cache)
                    
                    tar_path.unlink()
                    console.print(f"[green] Python {best_version} Linux téléchargé[/green]")
                    
                except Exception as e:
                    console.print(f"[red] Erreur téléchargement: {e}[/red]")
                    return False
            
            python_path = python_cache / "python"
            if not python_path.exists():
                python_path = python_cache
        
        # Copier Python
        console.print(f"[cyan] Copie de Python {best_version} pour {target_os}...[/cyan]")
        target_dir = deploy_dir / f"python-{best_version}"
        shutil.copytree(python_path, target_dir)
        
        # Adapter les scripts pour utiliser la bonne version
        if target_os == 'linux':
            for file in target_dir.rglob('*'):
                if file.is_file() and ('bin' in str(file) or file.suffix == ''):
                    try:
                        file.chmod(0o755)
                    except:
                        pass
        
        # Si on a utilisé la version originale, supprimer le fallback
        if best_version == python_version and fallback_file.exists():
            fallback_file.unlink()
            console.print(f"[green] Version originale {python_version} maintenant disponible![/green]")
        
        return True

    def create_deployment_package(self):
        """Créer le package de déploiement complet"""
        console.print("[cyan] Création du package de déploiement...[/cyan]")
        
        # Obtenir la version et créer le nom du package
        version = self.get_project_version()
        date_str = datetime.now().strftime('%Y%m%d')
        package_name = f"{self.project_name}-v{version}-{date_str}.zip"
        
        # Créer le dossier packages s'il n'existe pas
        packages_dir = Path("packages")
        packages_dir.mkdir(exist_ok=True)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            deploy_dir = Path(temp_dir) / "deploy"
            deploy_dir.mkdir()
            
            # Copier les fichiers du projet
            files_to_copy = ['main.py', 'pyproject.toml', '.python-version', 'requirements.txt', 'README.md']
            for file in files_to_copy:
                src = self.project_path / file
                if src.exists():
                    shutil.copy2(src, deploy_dir / file)
                    console.print(f"   Copié: {file}")
            
            # Copier les dossiers si présents
            for folder in ['src', 'templates', 'static', 'config']:
                src_folder = self.project_path / folder
                if src_folder.exists():
                    shutil.copytree(src_folder, deploy_dir / folder)
                    console.print(f"   Copié dossier: {folder}")
            
            # Ajouter UV
            if not self.download_uv(deploy_dir):
                return None
            
            # Ajouter Python
            python_version = self.get_python_version()
            if not self.copy_python(deploy_dir, python_version):
                return None
            
            # Créer les scripts selon l'OS
            self.create_batch_scripts(deploy_dir, python_version)
            
            # Créer le ZIP avec le nouveau nom
            zip_path = packages_dir / package_name
            console.print(f"[cyan] Compression du package: {package_name}[/cyan]")
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                files = list(deploy_dir.rglob('*'))
                with Progress() as progress:
                    task = progress.add_task("[cyan]Compression...", total=len(files))
                    for file in files:
                        if file.is_file():
                            zipf.write(file, file.relative_to(deploy_dir))
                            progress.update(task, advance=1)
            
            size_mb = zip_path.stat().st_size / (1024 * 1024)
            console.print(f"[green] Package créé: {zip_path.absolute()}[/green]")
            console.print(f"[dim]    Taille: {size_mb:.1f} MB | Version: {version} | Date: {date_str}[/dim]")
            return zip_path
    
    def create_batch_scripts(self, deploy_dir, python_version):
        """Créer les scripts selon l'OS cible"""
        target_os = self.server_config.get('os', 'windows').lower()
        
        # NOUVEAU : Déterminer la version réelle utilisée
        if target_os == 'linux':
            # Chercher le dossier python-* réellement créé
            python_dirs = list(deploy_dir.glob('python-*'))
            if python_dirs:
                # Extraire la version du nom du dossier
                actual_version = python_dirs[0].name.replace('python-', '')
            else:
                actual_version = python_version
        else:
            actual_version = python_version
        
        if target_os == 'windows':
            # Scripts batch pour Windows
            # Setup.bat
            setup_template = Path("templates/setup.bat.template")
            if setup_template.exists():
                content = setup_template.read_text()
                content = content.replace('{python_version}', actual_version)
                (deploy_dir / "setup.bat").write_text(content)
            else:
                (deploy_dir / "setup.bat").write_text(f'''@echo off
echo Installation de l'environnement Python...
uv.exe venv --python python-{actual_version}\\python.exe
echo Environnement cree avec succes!
''')
            
            # Run.bat reste inchangé
            run_template = Path("templates/run.bat.template")
            if run_template.exists():
                content = run_template.read_text()
                content = content.replace('{project_name}', self.project_name)
                content = content.replace('{main_file}', 'main.py')
                (deploy_dir / "run.bat").write_text(content)
            else:
                (deploy_dir / "run.bat").write_text('''@echo off
.venv\\Scripts\\python.exe main.py
pause
''')
            console.print("   Scripts batch créés")
            
        else:  # Linux
            # Scripts shell pour Linux avec la version réelle
            setup_content = f'''#!/bin/bash
echo "========================================"
echo "Installation de l'environnement Python"
echo "========================================"
echo ""
./uv venv --python python-{actual_version}/bin/python
echo ""
echo "Environnement créé avec succès!"
echo "========================================"
'''
            (deploy_dir / "setup.sh").write_bytes(setup_content.encode('utf-8'))
            
            # run.sh reste inchangé
            run_content = f'''#!/bin/bash
echo "========================================"
echo "Exécution de {self.project_name}"
echo "========================================"
echo ""
.venv/bin/python main.py
echo ""
echo "Appuyez sur Entrée pour continuer..."
read
'''
            (deploy_dir / "run.sh").write_bytes(run_content.encode('utf-8'))
            
            # Rendre exécutables
            (deploy_dir / "setup.sh").chmod(0o755)
            (deploy_dir / "run.sh").chmod(0o755)
            
            console.print(f"   Scripts shell créés (Python {actual_version})")

    def transfer_package(self, package_path):
        """Transférer le package sur le serveur avec support package_path"""
        # Utiliser package_path si défini, sinon deploy_path
        package_dir = self.server_config.get('package_path', self.server_config['deploy_path'])
        deploy_dir = self.server_config['deploy_path']
        
        # Adapter les séparateurs selon l'OS
        if self.server_config.get('os', 'windows').lower() == 'windows':
            package_dir = package_dir.replace('/', '\\')
            deploy_dir = deploy_dir.replace('/', '\\')
            sep = '\\'
            final_dir = f"{deploy_dir}\\{self.project_name}"
        else:
            package_dir = package_dir.replace('\\', '/')
            deploy_dir = deploy_dir.replace('\\', '/')
            sep = '/'
            final_dir = f"{deploy_dir}/{self.project_name}"
        
        remote_zip = f"{package_dir}{sep}{package_path.name}"
        
        # Créer les dossiers distants
        console.print(f"[cyan] Création des dossiers distants...[/cyan]")
        
        # Créer package_dir si nécessaire
        if self.server_config.get('os', 'windows').lower() == 'windows':
            mkdir_cmd = f'if not exist "{package_dir}" mkdir "{package_dir}"'
        else:
            mkdir_cmd = f'mkdir -p "{package_dir}"'
        
        stdin, stdout, stderr = self.ssh.exec_command(mkdir_cmd)
        stdout.read()
        
        # Créer le dossier de déploiement final
        if self.server_config.get('os', 'windows').lower() == 'windows':
            mkdir_cmd = f'if not exist "{final_dir}" mkdir "{final_dir}"'
        else:
            mkdir_cmd = f'mkdir -p "{final_dir}"'
            
        stdin, stdout, stderr = self.ssh.exec_command(mkdir_cmd)
        stdout.read()
        
        # Transférer le fichier
        console.print(f"[cyan] Transfert vers: {package_dir}[/cyan]")
        file_size = package_path.stat().st_size
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
        ) as progress:
            task = progress.add_task(f"[cyan]Transfert de {package_path.name}...", total=file_size)
            
            with open(package_path, 'rb') as local_file:
                remote_path = remote_zip.replace('\\', '/')
                with self.sftp.open(remote_path, 'wb') as remote_file:
                    while True:
                        data = local_file.read(32768)
                        if not data:
                            break
                        remote_file.write(data)
                        progress.update(task, advance=len(data))
        
        console.print("[green] Package transféré[/green]")
        
        # Extraire dans le dossier final
        console.print(f"[cyan] Extraction vers: {final_dir}[/cyan]")
        
        if self.server_config.get('os', 'windows').lower() == 'windows':
            extract_cmd = f'cd "{final_dir}" && tar -xf "{remote_zip}"'
        else:
            extract_cmd = f'cd "{final_dir}" && tar -xzf "{remote_zip}" 2>/dev/null || unzip -q "{remote_zip}"'
        
        stdin, stdout, stderr = self.ssh.exec_command(extract_cmd)
        stdout.read()
        console.print("[green] Package extrait[/green]")
        
        # AJOUT : Corriger les permissions sur Linux
        if self.server_config.get('os', 'windows').lower() == 'linux':
            console.print("[cyan] Configuration des permissions Linux...[/cyan]")
            
            # Rendre exécutables : uv, scripts, et binaires Python
            chmod_commands = [
                f'cd "{final_dir}" && chmod +x uv 2>/dev/null',
                f'cd "{final_dir}" && chmod +x *.sh 2>/dev/null',
                f'cd "{final_dir}" && find python-* -type d -name bin -exec chmod -R +x {{}} \; 2>/dev/null',
                f'cd "{final_dir}" && chmod -R +x python-*/bin/* 2>/dev/null'
            ]
            
            for cmd in chmod_commands:
                stdin, stdout, stderr = self.ssh.exec_command(cmd)
                stdout.read()
            
            console.print("[green] Permissions configurées[/green]")
        
        # Nettoyer si demandé
        if self.server_config.get('cleanup_package', True):
            console.print("[cyan] Nettoyage du package...[/cyan]")
            if self.server_config.get('os', 'windows').lower() == 'windows':
                cleanup_cmd = f'del "{remote_zip}"'
            else:
                cleanup_cmd = f'rm -f "{remote_zip}"'
            
            stdin, stdout, stderr = self.ssh.exec_command(cleanup_cmd)
            stdout.read()
            console.print("[dim]Package supprimé[/dim]")
        else:
            console.print(f"[dim]Package conservé dans: {package_dir}[/dim]")
        
        # Exécuter le script d'installation approprié
        console.print("[cyan] Installation de l'environnement...[/cyan]")
        
        if self.server_config.get('os', 'windows').lower() == 'windows':
            setup_script = 'setup.bat'
        else:
            setup_script = 'chmod +x setup.sh && ./setup.sh'
        
        stdin, stdout, stderr = self.ssh.exec_command(f'cd "{final_dir}" && {setup_script}')
        output = stdout.read().decode()
        if output:
            for line in output.splitlines():
                if line.strip():
                    console.print(f"  [dim]{line}[/dim]")
        
        return True

    def test_deployment(self):
        """Tester le déploiement"""
        console.print("[cyan] Test du déploiement...[/cyan]")
        
        deploy_dir = self.server_config['deploy_path']
        
        # Adapter selon l'OS
        if self.server_config.get('os', 'windows').lower() == 'windows':
            final_dir = f"{deploy_dir}\\{self.project_name}"
            test_cmd = f'cd "{final_dir}" && .venv\\Scripts\\python.exe main.py'
        else:
            final_dir = f"{deploy_dir}/{self.project_name}"
            test_cmd = f'cd "{final_dir}" && .venv/bin/python main.py'
        
        stdin, stdout, stderr = self.ssh.exec_command(test_cmd)
        output = stdout.read().decode()
        error = stderr.read().decode()
        
        if output:
            console.print("[green] Sortie du programme:[/green]")
            for line in output.splitlines():
                console.print(f"  {line}")
        
        if error:
            console.print("[red] Erreurs:[/red]")
            for line in error.splitlines():
                console.print(f"  {line}")
        
        return bool(output) and not bool(error)
    
    def run(self):
        """Exécuter le déploiement complet"""
        # Se connecter
        if not self.connect():
            return False
        
        try:
            # Créer le package
            package_path = self.create_deployment_package()
            if not package_path:
                console.print("[red] Échec de création du package[/red]")
                return False
            
            # Transférer et installer
            if not self.transfer_package(package_path):
                console.print("[red] Échec du transfert[/red]")
                return False
            
            # Tester
            if self.test_deployment():
                console.print("[bold green] Déploiement terminé avec succès ![/bold green]")
                return True
            else:
                console.print("[yellow] Déploiement effectué mais le test a échoué[/yellow]")
                return False
            
        finally:
            if self.ssh:
                self.ssh.close()
                console.print("[dim]Connexion fermée[/dim]")

@click.command()
@click.option('--project', '-p', required=False, help='Nom du projet à déployer')
@click.option('--server', '-s', help='Nom du serveur cible')
@click.option('--group', '-g', help='Groupe de serveurs à déployer')
@click.option('--list-projects', '-l', is_flag=True, help='Lister les projets disponibles')
@click.option('--list-packages', '-lp', is_flag=True, help='Lister les packages créés')
@click.option('--list-servers', '-ls', is_flag=True, help='Lister les serveurs configurés')
@click.option('--password', help='Mot de passe (éviter en production)')
def deploy(project, server, group, list_projects, list_packages, list_servers, password):
    """
     UV Deploy Tools - Déploiement automatisé de projets Python
    
    Exemples:
        deploy.py -p mon-projet -s test
        deploy.py -p mon-projet -g production
        deploy.py -l  # Liste les projets
        deploy.py -ls # Liste les serveurs
    """
    
    # Charger la configuration
    config_file = Path("configs/servers.yaml")
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    if list_servers:
        # Lister les serveurs configurés
        servers = config.get('servers', {})
        groups = config.get('groups', {})
        
        if servers:
            table = Table(title="Serveurs configurés")
            table.add_column("Nom", style="cyan")
            table.add_column("Host", style="yellow") 
            table.add_column("OS", style="green")
            table.add_column("User", style="magenta")
            table.add_column("Deploy Path", style="blue")
            
            for name, srv in servers.items():
                os_type = srv.get('os', 'windows')
                table.add_row(
                    name,
                    f"{srv['host']}:{srv.get('port', 22)}",
                    os_type,
                    srv['user'],
                    srv.get('deploy_path', 'N/A')
                )
            console.print(table)
        
        if groups:
            table = Table(title="Groupes configurés")
            table.add_column("Groupe", style="cyan")
            table.add_column("Serveurs", style="yellow")
            
            for name, servers in groups.items():
                table.add_row(name, ", ".join(servers))
            console.print(table)
        return
    
    if list_packages:
        # Lister les packages existants
        packages_dir = Path("packages")
        if packages_dir.exists():
            packages = list(packages_dir.glob("*.zip"))
            if packages:
                table = Table(title="Packages disponibles")
                table.add_column("Nom", style="cyan")
                table.add_column("Taille", style="yellow")
                table.add_column("Date", style="green")
                
                for pkg in sorted(packages, reverse=True):
                    size_mb = pkg.stat().st_size / (1024 * 1024)
                    date = datetime.fromtimestamp(pkg.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
                    table.add_row(pkg.name, f"{size_mb:.1f} MB", date)
                
                console.print(table)
            else:
                console.print("[yellow]Aucun package trouvé[/yellow]")
        else:
            console.print("[yellow]Le dossier packages n'existe pas encore[/yellow]")
        return
    
    if list_projects:
        # Lister les projets disponibles
        parent_dir = Path("..")
        projects = [d.name for d in parent_dir.iterdir() 
                   if d.is_dir() and (d / "pyproject.toml").exists()]
        
        table = Table(title="Projets disponibles")
        table.add_column("Nom", style="cyan")
        table.add_column("Python", style="yellow")
        table.add_column("Version", style="green")
        
        for proj in projects:
            py_version = ""
            py_file = parent_dir / proj / ".python-version"
            if py_file.exists():
                py_version = py_file.read_text().strip()
            
            # Lire la version du projet
            proj_version = "?"
            pyproject = parent_dir / proj / "pyproject.toml"
            if pyproject.exists():
                try:
                    import tomllib
                except ImportError:
                    try:
                        import tomli as tomllib
                    except ImportError:
                        tomllib = None
                
                if tomllib:
                    with open(pyproject, 'rb') as f:
                        data = tomllib.load(f)
                        proj_version = data.get('project', {}).get('version', '0.1.0')
            
            table.add_row(proj, py_version, proj_version)
        
        console.print(table)
        return
    
    if not project:
        console.print("[red] Veuillez spécifier un projet avec --project[/red]")
        console.print("[yellow]Utilisez --help pour voir les options disponibles[/yellow]")
        return
    
    # Gérer les groupes
    if group:
        groups = config.get('groups', {})
        if group not in groups:
            console.print(f"[red] Groupe '{group}' non trouvé[/red]")
            return
        
        servers_to_deploy = groups[group]
        console.print(f"[cyan] Déploiement sur le groupe '{group}': {', '.join(servers_to_deploy)}[/cyan]")
    elif server:
        servers_to_deploy = [server]
    else:
        # Pas de serveur spécifié, proposer un choix
        servers = list(config.get('servers', {}).keys())
        if not servers:
            console.print("[red] Aucun serveur configuré[/red]")
            return
        
        if len(servers) == 1:
            servers_to_deploy = servers
            console.print(f"[cyan]Utilisation du seul serveur configuré: {servers[0]}[/cyan]")
        else:
            console.print("[yellow]Plusieurs serveurs disponibles:[/yellow]")
            for i, srv in enumerate(servers, 1):
                console.print(f"  {i}. {srv}")
            console.print("[yellow]Utilisez -s <nom> pour spécifier un serveur[/yellow]")
            return
    
    # Déployer sur chaque serveur
    failed = []
    succeeded = []
    
    for srv in servers_to_deploy:
        console.print(f"\\n[bold cyan] Déploiement sur {srv}[/bold cyan]")
        console.print(f"[yellow] Projet: {project}[/yellow]\\n")
        
        try:
            deployer = OrbitDeployer(project, srv, password)
            if deployer.run():
                succeeded.append(srv)
            else:
                failed.append(srv)
        except Exception as e:
            console.print(f"[red] Erreur lors du déploiement sur {srv}: {e}[/red]")
            failed.append(srv)
    
    # Résumé si plusieurs serveurs
    if len(servers_to_deploy) > 1:
        console.print("\\n[bold] Résumé du déploiement:[/bold]")
        if succeeded:
            console.print(f"[green] Réussi: {', '.join(succeeded)}[/green]")
        if failed:
            console.print(f"[red] Échoué: {', '.join(failed)}[/red]")

if __name__ == "__main__":
    deploy()








