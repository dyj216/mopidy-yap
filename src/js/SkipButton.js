import {Badge, IconButton, Tooltip} from "@mui/material";
import {SkipNext} from "@mui/icons-material";
import React from "react";

export function SkipButton(props) {
  return <Tooltip title="Skip">
    <Badge badgeContent={props.skipCount} color="primary">
      <IconButton color="primary" size="large" onClick={props.onClick}>
        <SkipNext/>
      </IconButton>
    </Badge>
  </Tooltip>;
}
