from pydantic import BaseModel, Field, field_validator


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    geo: str = Field(min_length=2, max_length=2)
    offer_id: int = Field(gt=0)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("geo")
    @classmethod
    def normalize_geo(cls, value: str) -> str:
        return value.upper()


class OfferAdd(BaseModel):
    offer_id: int = Field(gt=0)


class PinUpdate(BaseModel):
    pinned: bool

