import json
import uuid
from langchain_core.tools import tool
from db.connection import fetch_all, fetch_one, execute


@tool
async def get_material(identifier: str) -> str:
    """Get material details by material ID or material number (e.g. MAT-0001)."""
    row = await fetch_one(
        'SELECT * FROM materials WHERE "materialNumber" = $1 OR "id" = $1',
        identifier,
    )
    if not row:
        return f"No material found with identifier: {identifier}"
    return json.dumps(row, indent=2)


@tool
async def list_materials(
    description: str = "",
    material_group: str = "",
    is_active: bool = True,
    min_price: float = 0,
    max_price: float = 999999999,
    limit: int = 50,
) -> str:
    """Search and filter materials. Returns at most `limit` rows (default 50). All parameters are optional."""
    conditions = ['"isActive" = $1']
    params: list = [is_active]
    idx = 2

    if description:
        conditions.append(f'"description" ILIKE ${idx}')
        params.append(f"%{description}%")
        idx += 1
    if material_group:
        conditions.append(f'"materialGroup" ILIKE ${idx}')
        params.append(f"%{material_group}%")
        idx += 1

    conditions.append(f'"basePrice" >= ${idx}')
    params.append(min_price)
    idx += 1
    conditions.append(f'"basePrice" <= ${idx}')
    params.append(max_price)

    where = " AND ".join(conditions)
    actual_limit = min(limit, 200)
    params.append(actual_limit)
    rows = await fetch_all(
        f'SELECT * FROM materials WHERE {where} ORDER BY "materialNumber" LIMIT ${len(params)}',
        *params,
    )
    if not rows:
        return "No materials found matching the criteria."
    return json.dumps(rows, indent=2)


@tool
async def create_material(
    description: str,
    material_group: str,
    base_price: float,
    unit_of_measure: str = "EA",
    weight: float = 0,
    weight_unit: str = "KG",
    currency: str = "USD",
) -> str:
    """Create a new material master record."""
    material_id = str(uuid.uuid4())

    last = await fetch_one(
        'SELECT "materialNumber" FROM materials ORDER BY "materialNumber" DESC LIMIT 1'
    )
    if last:
        num = int(last["materialNumber"].split("-")[1]) + 1
        material_number = f"MAT-{num:04d}"
    else:
        material_number = "MAT-0001"

    await execute(
        """INSERT INTO materials
           ("id","materialNumber","description","materialGroup","unitOfMeasure",
            "weight","weightUnit","basePrice","currency","isActive","createdAt","updatedAt")
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,true,NOW(),NOW())""",
        material_id, material_number, description, material_group,
        unit_of_measure, weight if weight > 0 else None, weight_unit,
        base_price, currency,
    )
    return json.dumps({
        "message": f"Material {material_number} ({description}) created successfully",
        "materialId": material_id,
        "materialNumber": material_number,
    })


@tool
async def update_material(
    identifier: str,
    description: str = "",
    material_group: str = "",
    base_price: float = -1,
    unit_of_measure: str = "",
    weight: float = -1,
    weight_unit: str = "",
    currency: str = "",
) -> str:
    """Update a material record. Only non-empty/non-default fields are applied."""
    mat = await fetch_one(
        'SELECT * FROM materials WHERE "materialNumber" = $1 OR "id" = $1',
        identifier,
    )
    if not mat:
        return f"No material found: {identifier}"

    updates, params = [], []
    idx = 1
    for col, val in {
        "description": description, "materialGroup": material_group,
        "unitOfMeasure": unit_of_measure, "weightUnit": weight_unit,
        "currency": currency,
    }.items():
        if val:
            updates.append(f'"{col}" = ${idx}')
            params.append(val)
            idx += 1
    if base_price >= 0:
        updates.append(f'"basePrice" = ${idx}')
        params.append(base_price)
        idx += 1
    if weight >= 0:
        updates.append(f'"weight" = ${idx}')
        params.append(weight)
        idx += 1

    if not updates:
        return "No fields to update."

    updates.append('"updatedAt" = NOW()')
    params.append(mat["id"])
    await execute(
        f'UPDATE materials SET {", ".join(updates)} WHERE "id" = ${idx}',
        *params,
    )
    return f"Material {mat['materialNumber']} updated successfully."


@tool
async def deactivate_material(identifier: str) -> str:
    """Deactivate (soft-delete) a material."""
    mat = await fetch_one(
        'SELECT "id","materialNumber" FROM materials WHERE "materialNumber" = $1 OR "id" = $1',
        identifier,
    )
    if not mat:
        return f"No material found: {identifier}"
    await execute(
        'UPDATE materials SET "isActive" = false, "updatedAt" = NOW() WHERE "id" = $1',
        mat["id"],
    )
    return f"Material {mat['materialNumber']} has been deactivated."


all_material_tools = [
    get_material,
    list_materials,
    create_material,
    update_material,
    deactivate_material,
]
