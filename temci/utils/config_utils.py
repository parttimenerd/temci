"""
Types shared between different file config definitions
"""

from temci.utils.typecheck import ListOrTuple, Dict, Optional, Str, Default, Description, Any

ATTRIBUTES_TYPE = Dict({
            "tags": ListOrTuple(Str()) // Default([]) // Description("Tags of this block"),
            "description": Optional(Str()) // Default("")
        }, unknown_keys=True, key_type=Str(), value_type=Any()) \
                  // Default({"tags": []}) \
                  // Description("Optional attributes that describe the block")