import React, {useEffect, useState} from "react";
import {
  Alert,
  Avatar,
  Box,
  CircularProgress,
  FormControl,
  Grid,
  IconButton,
  InputAdornment,
  InputLabel,
  List,
  ListItem,
  ListItemAvatar,
  ListItemButton,
  ListItemText,
  OutlinedInput
} from "@mui/material";
import {Add, Search} from "@mui/icons-material";
import {printTrackLength} from "./Playlist";

function SearchResults(props) {
  return (
    <List>
      {props.results.map(track => (
        <ListItem key={track.uri}>
          <ListItemButton onClick={() => props.addTrack(track)}>
            <ListItemAvatar>
              <Avatar sx={{bgcolor: "primary.main"}}>
                <Add/>
              </Avatar>
            </ListItemAvatar>
            <ListItemText
              primary={track.name + " " + printTrackLength(track)}
              secondary={track.artists.map(a => a.name).join(', ') + ' - ' + track.album.name}
            />
          </ListItemButton>
        </ListItem>
      ))}
    </List>
  );
}

export function SearchComponent(props) {
  const [results, setResults] = useState([]);
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isError, setIsError] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      setIsError(false);
      setIsLoading(true)
      try {
        const data = await props.mopidy.library.search({
          'query': {
            'any': [search]
          }
        });
        let tracks = [];
        for (const searchResult of data.reverse()) {
          if (searchResult.tracks) {
            tracks.push(...searchResult.tracks);
          }
        }
        setResults(tracks);
      } catch (e) {
        setIsError(true);
        console.log(e);
      }
      setIsLoading(false);
    };
    if (props.mopidy.library && search !== "") {
      fetchData();
    }
  }, [search, props.mopidy]);

  async function addTrack(track) {
    if (props.mopidy.tracklist) {
      await props.mopidy.tracklist.add({tracks: [track]});
      if (await props.mopidy.playback.getState() !== "playing") {
        await props.mopidy.playback.play({});
      }
    }
  }

  return (
    <React.Fragment>
      <Grid item xs={12}>
        <FormControl fullWidth variant="outlined" component="form" onSubmit={event => {
          setSearch(query);
          event.preventDefault();
        }}>
          <InputLabel htmlFor="search-field">Search</InputLabel>
          <OutlinedInput
            value={query}
            onChange={event => setQuery(event.target.value)}
            id="search-field"
            type="search"
            label="search"
            endAdornment={
              <InputAdornment position="end">
                <IconButton
                  aria-label="search"
                  onClick={() => setSearch(query)}
                >
                  <Search/>
                </IconButton>
              </InputAdornment>
            }
          />
        </FormControl>
      </Grid>
      <Grid item xs={12}>
        {isError && <Alert severity="error">Something went wrong ...</Alert>}
        {
          isLoading ?
            <Box sx={{ display: 'flex' }} justifyContent="center">
              <CircularProgress />
            </Box>
            : <SearchResults results={results} addTrack={addTrack}/>
        }
      </Grid>
    </React.Fragment>
  );
}
