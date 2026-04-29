import subprocess
import json
import sys
import time

def check_containers():
    print("Vérificando estado de los contenedores de BLOQUE HUB...")
    
    try:
        # Ejecuta docker compose ps en formato JSON para análisis programático
        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # En algunas versiones de Docker, devuelve múltiples objetos JSON, uno por línea
        containers = [json.loads(line) for line in result.stdout.strip().split('\n') if line]
        
        all_healthy = True
        for container in containers:
            name = container.get("Service", "Unknown")
            status = container.get("Status", "Unknown")
            health = container.get("Health", "N/A")
            
            print(f"[*] Servicio: {name:15} | Estado: {status:10} | Salud: {health}")
            
            # Criterio de fallo: si no está corriendo o si el healthcheck es 'unhealthy'
            if "running" not in status.lower() or "unhealthy" in health.lower():
                all_healthy = False
        
        return all_healthy

    except Exception as e:
        print(f"Error al conectar con Docker: {e}")
        return False

if __name__ == "__main__":
    # Reintento simple para dar tiempo a los healthchecks
    for i in range(3):
        if check_containers():
            print("\n✅ ¡Infraestructura validada con éxito!")
            sys.exit(0)
        print(f"\n[!] Algunos servicios no están listos. Reintentando en 10s... ({i+1}/3)")
        time.sleep(10)
    
    print("\n❌ Error: La infraestructura no alcanzó un estado estable.")
    sys.exit(1)