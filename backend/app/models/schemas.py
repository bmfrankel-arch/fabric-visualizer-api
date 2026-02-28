from pydantic import BaseModel
from datetime import datetime


class FabricOut(BaseModel):
    id: int
    name: str
    filename: str
    category: str
    color_tags: str
    created_at: str


class FurnitureOut(BaseModel):
    id: int
    name: str
    filename: str
    source_url: str
    source_site: str
    category: str
    created_at: str


class VisualizationOut(BaseModel):
    id: int
    fabric_id: int
    furniture_id: int
    result_filename: str
    created_at: str


class ScraperConfig(BaseModel):
    site_name: str
    base_url: str
    product_selector: str = ""
    image_selector: str = ""
    name_selector: str = ""
    enabled: bool = True


class ScraperConfigOut(ScraperConfig):
    id: int


class VisualizeRequest(BaseModel):
    fabric_id: int
    furniture_id: int
