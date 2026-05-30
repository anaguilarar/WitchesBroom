from pydantic import BaseModel, Field, model_validator, field_validator
from typing import Annotated, Optional, List, Dict, Any
from pathlib import Path


class ClimateIndex(BaseModel):
    """
    Climate index configuration (e.g., SPI, SPEI, ScPDSI).
    """
    name: str
    description: Optional[str] = None
    meteorological_variables: List[str]
    parameters: Optional[Dict[str, Any]] = None


class ClimateSummarisation(BaseModel):
    """
    Configuration for basic structural aggregation functions over climate layers.
    """
    description: Optional[str] = None
    meteorological_variable: str 
    summary_function: str  # e.g., "mean", "sum", "max", "min", "std"
    parameters: Optional[Dict[str, Any]] = None

    # Improvement 1: Protect summary_function names against typos at initialization
    @field_validator('summary_function')
    @classmethod
    def validate_summary_function(cls, v: str) -> str:
        allowed = {"mean", "sum", "max", "min", "std", "median", "var"}
        v_lower = v.lower().strip()
        if v_lower not in allowed:
            raise ValueError(
                f"Unsupported summary_function '{v}'. Must be one of {allowed}"
            )
        return v_lower


class ClimateConfig(BaseModel):
    """
    Consolidated configuration for environmental input data engines.
    """
    climate_data_path: Annotated[Path, Field(description='Root path to the input climate dataset directory')]
    indices: List[ClimateIndex] = Field(default_factory=list)
    summarizations: List[ClimateSummarisation] = Field(default_factory=list)
    

class GeneralInfoConfig(BaseModel):
    """
    Global process execution parameters.
    """
    n_cores: Annotated[int, Field(description='Number of CPU cores to allocate for parallel worker pools')]
    output_path: Annotated[Path, Field(description='Directory path where final results will be serialized')]
    year_oi: Annotated[Optional[int], Field(default=None, description="Year of interest for filtering climate data layers (e.g., 2014). If None, no year-based filtering will be applied.")]
    
    spatial_data_path: Annotated[
        Optional[Path], 
        Field(default=None, description="Path to coordinate layers (e.g., shapefile/GeoJSON) for zonal/point extractions.")
    ]

    # Improvement 2: Prevent thread-pool collapse bugs
    @field_validator('n_cores')
    @classmethod
    def validate_cores(cls, v: int) -> int:
        if v < -1 or v == 0:
            raise ValueError("n_cores must be a positive integer, or -1 to utilize all available processors.")
        return v


class DataSummarizationConfig(BaseModel):
    """
    Configuration details handling temporal clipping and agricultural/experimental timeline syncs.
    """
    field_data_source: Annotated[
        Path, 
        Field(description="Source file mapping experimental observation sites to rows")
    ]
    column_starting_date: Annotated[Optional[str], Field(default=None)]
    column_ending_date: Annotated[Optional[str], Field(default=None)]
    temporal_window: Annotated[Optional[int], Field(default=6)]
    nmonths_lookahead: Annotated[Optional[int], Field(default=0)]
    nmonths_lookback: Annotated[Optional[int], Field(default=6)]
    output_filename: Annotated[Optional[str], Field(default="extracted_climate_data.csv", description="Filename for the extracted climate data CSV output")]
    
    @model_validator(mode='after')
    def validate_date_columns(self) -> 'DataSummarizationConfig':
        if self.field_data_source and not (self.column_starting_date or self.column_ending_date):
            raise ValueError(
                "When 'field_data_source' is provided, you must provide either "
                "'column_starting_date' or 'column_ending_date' to execute aggregations."
            )
        return self


class PipelineConfig(BaseModel):
    """
    Master declarative profile orchestrating the complete calculation graph.
    """
    general_info: GeneralInfoConfig
    climate_config: ClimateConfig
    data_summarization: DataSummarizationConfig