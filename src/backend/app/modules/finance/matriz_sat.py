"""
Matriz de compatibilidad SAT: régimen_fiscal × uso_cfdi (Anexo 20, CFDI 4.0).
Validación pre-timbrado para evitar rechazos del PAC.
"""

RFC_PUBLICO_GENERAL = "XAXX010101000"
USO_CFDI_DEFAULT = "G03"

MATRIZ_COMPATIBILIDAD_SAT: dict[str, list[str]] = {
    "601": ["G01", "G02", "G03", "I01", "I02", "I03", "I04", "I05", "I06", "I08", "S01", "CP01"],
    "603": ["G01", "G03", "I01", "I04", "S01", "CP01"],
    "605": ["G01", "G02", "G03", "I01", "I02", "I03", "I04", "I05", "I06", "I08",
            "D01", "D02", "D03", "D04", "D05", "D06", "D07", "D08", "D09", "D10", "S01", "CP01"],
    "606": ["G01", "G02", "G03", "I01", "I02", "I03", "I04", "I05", "I06", "I08",
            "D01", "D03", "D04", "D05", "D06", "D07", "D08", "D09", "D10", "S01", "CP01"],
    "608": ["G01", "G02", "G03", "I01", "I02", "I03", "I04", "I05", "I06", "I08",
            "D01", "D03", "D04", "D05", "D06", "D07", "D08", "D09", "D10", "S01", "CP01"],
    "612": ["G01", "G02", "G03", "I01", "I02", "I03", "I04", "I05", "I06", "I08",
            "D01", "D02", "D03", "D04", "D05", "D06", "D07", "D08", "D09", "D10", "S01", "CP01"],
    "616": ["S01"],
    "621": ["G01", "G02", "G03", "I01", "I02", "I03", "I04", "I05", "I06", "I08", "S01", "CP01"],
    "622": ["G01", "G02", "G03", "I01", "I02", "I03", "I04", "I05", "I06", "I08", "S01", "CP01"],
    "623": ["G01", "G02", "G03", "I01", "I02", "I03", "I04", "I05", "I06", "I08", "S01", "CP01"],
    "624": ["G01", "G02", "G03", "I01", "I02", "I03", "I04", "I05", "I06", "I08", "S01", "CP01"],
    "625": ["G01", "G02", "G03", "I01", "I02", "I03", "I04", "I05", "I06", "I08",
            "D01", "D02", "D03", "D04", "D05", "D06", "D07", "D08", "D09", "D10", "S01", "CP01"],
    "626": ["G01", "G02", "G03", "I01", "I02", "I03", "I04", "I05", "I06", "I08", "S01", "CP01"],
}


def validar_compatibilidad_regimen_uso_cfdi(
    regimen: str, uso_cfdi: str, rfc: str
) -> str | None:
    """
    Verifica que la combinación régimen_fiscal_receptor × uso_cfdi sea válida (Anexo 20 SAT).
    Retorna mensaje de error si hay incompatibilidad, None si es válido.
    """
    if rfc == RFC_PUBLICO_GENERAL and uso_cfdi != "S01":
        return (
            f"USO_CFDI_INCOMPATIBLE: RFC público en general ({RFC_PUBLICO_GENERAL}) "
            f"solo permite uso S01 (Sin efectos fiscales). Recibido: {uso_cfdi}."
        )
    usos_permitidos = MATRIZ_COMPATIBILIDAD_SAT.get(regimen)
    if usos_permitidos is None:
        return (
            f"REGIMEN_FISCAL_NO_RECONOCIDO: El régimen \"{regimen}\" no está en la matriz "
            f"de compatibilidad del SAT. Verificar con Finanzas antes de timbrar."
        )
    if uso_cfdi not in usos_permitidos:
        return (
            f"USO_CFDI_INCOMPATIBLE: El uso \"{uso_cfdi}\" no es compatible con el régimen "
            f"\"{regimen}\". Usos permitidos: {usos_permitidos}."
        )
    return None
