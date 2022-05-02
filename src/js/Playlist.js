import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Badge,
  IconButton,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
} from "@mui/material";
import {Delete, ExpandMore, KeyboardArrowUp, PlayArrow} from "@mui/icons-material";
import React from "react";

export function printTrackLength(track){

    if(!track.length)
      return '';

    const _sum = parseInt(track.length / 1000);
    const _min = parseInt(_sum / 60);
    const _sec = _sum % 60;

    return '(' + _min + ':' + (_sec < 10 ? '0' + _sec : _sec) + ')' ;
}

function removeTrack(revelry, tlid) {
  const payload = JSON.stringify({action: "vote_to_delete", payload: {track_id: tlid}});
  revelry.send(payload);
}

function setAsNextTrack(revelry, tlid) {
  const payload = JSON.stringify({action: "vote_to_top", payload: {track_id: tlid}});
  revelry.send(payload);
}

export function Playlist(props) {
  const currentTrackName = props.trackInfo.name ? props.trackInfo.name : "Nothing is playing";
  const currentTrackArtistAndAlbum = props.trackInfo.artists
    ? props.trackInfo.artists + " - " + props.trackInfo.album
    : "Add a track to party!";

  return <Accordion>
    <AccordionSummary
      expandIcon={<ExpandMore/>}
      aria-controls="playlist-content"
      id="playlist-header"
    >
      <ListItem>
        <ListItemAvatar>
          <PlayArrow/>
        </ListItemAvatar>
        <ListItemText
          primary={currentTrackName + " " + printTrackLength(props.trackInfo)}
          secondary={currentTrackArtistAndAlbum}
        />
      </ListItem>
    </AccordionSummary>
    <AccordionDetails>
      {props.trackList.length > 1 ? <List>
        {props.trackList.slice(1).map(track => (
          <ListItem
            key={track.tlid}
            secondaryAction={
              <IconButton edge="end" aria-label="delete" onClick={() => removeTrack(props.revelry, track.tlid)}>
                <Badge badgeContent={props.deleteCount[track.tlid]} color="primary">
                  <Delete/>
                </Badge>
              </IconButton>
            }
          >
            <ListItemAvatar>
              <IconButton color="primary" size="large" onClick={() => setAsNextTrack(props.revelry, track.tlid)}>
                <Badge badgeContent={props.moveToTopCount[track.tlid]} color="primary">
                  <KeyboardArrowUp/>
                </Badge>
              </IconButton>
            </ListItemAvatar>
            <ListItemText
              primary={track.track.name + " " + printTrackLength(track.track)}
              secondary={track.track.artists.map(a => a.name).join(', ') + ' - ' + track.track.album.name}
            />
          </ListItem>
        ))}
      </List> : "There is no next track!"}
    </AccordionDetails>
  </Accordion>;
}
