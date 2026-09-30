"""HTTP routes for layers, objects, typed properties, tags, and URLs."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from sample_db_backend.schemas import (
    Layer,
    LayerCreate,
    LayerList,
    LayerObject,
    LayerUpdate,
    ObjectCreate,
    ObjectList,
    ObjectProperty,
    ObjectUpdate,
    ObjectUrl,
    ObjectUrlCreate,
    ObjectUrlList,
    ObjectUrlUpdate,
    PropertyCreate,
    PropertyList,
    PropertyUpdate,
    Tag,
    TagCreate,
    TagList,
    TagUpdate,
)
from sample_db_backend.services import layers as svc
from sample_db_backend.services.layers import ConflictError, NotFoundError

router = APIRouter()


def _nf(exc: NotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")


def _cf(exc: ConflictError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Conflict: {exc}")


@router.get("/layers", response_model=LayerList, tags=["layers"])
def list_layers(limit: int = Query(default=50, ge=1, le=100)) -> LayerList:
    """List map layers."""
    return LayerList(items=svc.list_layers(limit=limit))


@router.post("/layers", response_model=Layer, status_code=201, tags=["layers"])
def create_layer(payload: LayerCreate) -> Layer:
    """Create a map layer (422 on validation errors)."""
    return svc.create_layer(payload)


@router.get("/layers/{layer_id}", response_model=Layer, tags=["layers"])
def get_layer(layer_id: UUID) -> Layer:
    """Get a layer."""
    try:
        return svc.get_layer(layer_id)
    except NotFoundError as exc:
        raise _nf(exc) from exc


@router.patch("/layers/{layer_id}", response_model=Layer, tags=["layers"])
def update_layer(layer_id: UUID, payload: LayerUpdate) -> Layer:
    """Partial-update a layer."""
    try:
        return svc.update_layer(layer_id, payload)
    except NotFoundError as exc:
        raise _nf(exc) from exc


@router.delete("/layers/{layer_id}", status_code=204, tags=["layers"])
def delete_layer(layer_id: UUID) -> None:
    """Delete a layer (cascades objects and children)."""
    try:
        svc.delete_layer(layer_id)
    except NotFoundError as exc:
        raise _nf(exc) from exc


@router.get("/layers/{layer_id}/objects", response_model=ObjectList, tags=["objects"])
def list_layer_objects(
    layer_id: UUID,
    limit: int = Query(default=100, ge=1, le=100),
) -> ObjectList:
    """List objects on a layer."""
    try:
        return ObjectList(items=svc.list_objects(layer_id, limit=limit))
    except NotFoundError as exc:
        raise _nf(exc) from exc


@router.post(
    "/layers/{layer_id}/objects",
    response_model=LayerObject,
    status_code=201,
    tags=["objects"],
)
def create_layer_object(layer_id: UUID, payload: ObjectCreate) -> LayerObject:
    """Create a GeoJSON object on a layer."""
    try:
        return svc.create_object(layer_id, payload)
    except NotFoundError as exc:
        raise _nf(exc) from exc


@router.get("/objects", response_model=ObjectList, tags=["objects"])
def list_objects(
    tag: str | None = None,
    limit: int = Query(default=100, ge=1, le=100),
) -> ObjectList:
    """List objects, optionally filtered by tag name."""
    return ObjectList(items=svc.list_objects(tag=tag, limit=limit))


@router.get("/objects/{object_id}", response_model=LayerObject, tags=["objects"])
def get_object(object_id: UUID) -> LayerObject:
    """Get one object."""
    try:
        return svc.get_object(object_id)
    except NotFoundError as exc:
        raise _nf(exc) from exc


@router.patch("/objects/{object_id}", response_model=LayerObject, tags=["objects"])
def update_object(object_id: UUID, payload: ObjectUpdate) -> LayerObject:
    """Update object geometry."""
    try:
        return svc.update_object(object_id, payload)
    except NotFoundError as exc:
        raise _nf(exc) from exc


@router.delete("/objects/{object_id}", status_code=204, tags=["objects"])
def delete_object(object_id: UUID) -> None:
    """Delete an object."""
    try:
        svc.delete_object(object_id)
    except NotFoundError as exc:
        raise _nf(exc) from exc


@router.get(
    "/objects/{object_id}/properties",
    response_model=PropertyList,
    tags=["properties"],
)
def list_properties(object_id: UUID) -> PropertyList:
    """List typed properties on an object."""
    try:
        return PropertyList(items=svc.list_properties(object_id))
    except NotFoundError as exc:
        raise _nf(exc) from exc


@router.post(
    "/objects/{object_id}/properties",
    response_model=ObjectProperty,
    status_code=201,
    tags=["properties"],
)
def create_property(object_id: UUID, payload: PropertyCreate) -> ObjectProperty:
    """Create a typed property (text|temporal|image|binary)."""
    try:
        return svc.create_property(object_id, payload)
    except NotFoundError as exc:
        raise _nf(exc) from exc
    except ConflictError as exc:
        raise _cf(exc) from exc


@router.get("/properties/{property_id}", response_model=ObjectProperty, tags=["properties"])
def get_property(property_id: UUID) -> ObjectProperty:
    """Get one property."""
    try:
        return svc.get_property(property_id)
    except NotFoundError as exc:
        raise _nf(exc) from exc


@router.patch("/properties/{property_id}", response_model=ObjectProperty, tags=["properties"])
def update_property(property_id: UUID, payload: PropertyUpdate) -> ObjectProperty:
    """Partial-update a property."""
    try:
        return svc.update_property(property_id, payload)
    except NotFoundError as exc:
        raise _nf(exc) from exc
    except ConflictError as exc:
        raise _cf(exc) from exc


@router.delete("/properties/{property_id}", status_code=204, tags=["properties"])
def delete_property(property_id: UUID) -> None:
    """Delete a property."""
    try:
        svc.delete_property(property_id)
    except NotFoundError as exc:
        raise _nf(exc) from exc


@router.get("/tags", response_model=TagList, tags=["tags"])
def list_tags(limit: int = Query(default=100, ge=1, le=100)) -> TagList:
    """List classification tags."""
    return TagList(items=svc.list_tags(limit=limit))


@router.post("/tags", response_model=Tag, status_code=201, tags=["tags"])
def create_tag(payload: TagCreate) -> Tag:
    """Create a tag."""
    try:
        return svc.create_tag(payload)
    except ConflictError as exc:
        raise _cf(exc) from exc


@router.get("/tags/{tag_id}", response_model=Tag, tags=["tags"])
def get_tag(tag_id: UUID) -> Tag:
    """Get a tag."""
    try:
        return svc.get_tag(tag_id)
    except NotFoundError as exc:
        raise _nf(exc) from exc


@router.patch("/tags/{tag_id}", response_model=Tag, tags=["tags"])
def update_tag(tag_id: UUID, payload: TagUpdate) -> Tag:
    """Rename a tag."""
    try:
        return svc.update_tag(tag_id, payload)
    except NotFoundError as exc:
        raise _nf(exc) from exc
    except ConflictError as exc:
        raise _cf(exc) from exc


@router.delete("/tags/{tag_id}", status_code=204, tags=["tags"])
def delete_tag(tag_id: UUID) -> None:
    """Delete a tag."""
    try:
        svc.delete_tag(tag_id)
    except NotFoundError as exc:
        raise _nf(exc) from exc


@router.get("/objects/{object_id}/tags", response_model=TagList, tags=["tags"])
def list_object_tags(object_id: UUID) -> TagList:
    """List tags on an object."""
    try:
        return TagList(items=svc.list_object_tags(object_id))
    except NotFoundError as exc:
        raise _nf(exc) from exc


@router.put("/objects/{object_id}/tags/{tag_id}", status_code=204, tags=["tags"])
def attach_tag(object_id: UUID, tag_id: UUID) -> None:
    """Attach a tag to an object."""
    try:
        svc.attach_tag(object_id, tag_id)
    except NotFoundError as exc:
        raise _nf(exc) from exc


@router.delete("/objects/{object_id}/tags/{tag_id}", status_code=204, tags=["tags"])
def detach_tag(object_id: UUID, tag_id: UUID) -> None:
    """Detach a tag from an object."""
    try:
        svc.detach_tag(object_id, tag_id)
    except NotFoundError as exc:
        raise _nf(exc) from exc


@router.get("/objects/{object_id}/urls", response_model=ObjectUrlList, tags=["urls"])
def list_urls(object_id: UUID) -> ObjectUrlList:
    """List ordered URLs for an object (distinct from typed image/binary props)."""
    try:
        return ObjectUrlList(items=svc.list_urls(object_id))
    except NotFoundError as exc:
        raise _nf(exc) from exc


@router.post(
    "/objects/{object_id}/urls",
    response_model=ObjectUrl,
    status_code=201,
    tags=["urls"],
)
def create_url(object_id: UUID, payload: ObjectUrlCreate) -> ObjectUrl:
    """Add a URL to an object's list."""
    try:
        return svc.create_url(object_id, payload)
    except NotFoundError as exc:
        raise _nf(exc) from exc


@router.get("/urls/{url_id}", response_model=ObjectUrl, tags=["urls"])
def get_url(url_id: UUID) -> ObjectUrl:
    """Get one URL row."""
    try:
        return svc.get_url(url_id)
    except NotFoundError as exc:
        raise _nf(exc) from exc


@router.patch("/urls/{url_id}", response_model=ObjectUrl, tags=["urls"])
def update_url(url_id: UUID, payload: ObjectUrlUpdate) -> ObjectUrl:
    """Partial-update a URL row."""
    try:
        return svc.update_url(url_id, payload)
    except NotFoundError as exc:
        raise _nf(exc) from exc


@router.delete("/urls/{url_id}", status_code=204, tags=["urls"])
def delete_url(url_id: UUID) -> None:
    """Delete a URL row."""
    try:
        svc.delete_url(url_id)
    except NotFoundError as exc:
        raise _nf(exc) from exc
