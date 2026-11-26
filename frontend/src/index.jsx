import Mopidy from "mopidy";
import React, {useEffect} from 'react';
import './index.css';
import {createRoot} from "react-dom/client";
import '@fontsource/roboto/400.css';
import CssBaseline from '@mui/material/CssBaseline';
import {BrightnessMedium, Close, Pause, PlayArrow} from "@mui/icons-material";
import {
  Container,
  createTheme,
  Fade,
  Grid,
  IconButton,
  Link,
  Snackbar,
  ThemeProvider,
  Tooltip,
  Typography,
  useMediaQuery
} from "@mui/material";
import {SkipButton} from "./js/SkipButton";
import {Playlist} from "./js/Playlist";
import {SearchComponent} from "./js/SearchComponent";


const mopidy = new Mopidy({
  webSocketUrl: `ws://${document.location.host}/mopidy/ws`,
});

const yap = new WebSocket(`ws://${document.location.host}/yap/ws`);

export function getTrackInfo(track) {
  if (track.tlid) {
    track = track.track;
  }
  const artists = track.artists ? track.artists.map((a) => a.name).join(", ") : "";
  const album = track.album ? track.album.name : "";

  return {
    artists,
    album,
    name: track.name,
    length: track.length ? track.length : null,
    uri: track.uri,
  }
}

window.mopidy = mopidy;

const ColorModeContext = React.createContext({ toggleColorMode: () => {} });

async function handleSkip(trackInfo) {
  if (trackInfo.name) {
    const payload = JSON.stringify({action: "vote_to_skip", payload: {track_name: trackInfo.name}});
    yap.send(payload);
  }
}

function handleTogglePlay(playing) {
  playing ? mopidy.playback.pause() : mopidy.playback.resume();
}

function Yap() {
  const colorMode = React.useContext(ColorModeContext);
  const [trackInfo, setTrackInfo] = React.useState({});
  const [trackList, setTrackList] = React.useState([]);
  const [openSnackbar, setOpenSnackbar] = React.useState(false);
  const [snackbarMessage, setSnackbarMessage] = React.useState("");
  const [skipCount, setSkipCount] = React.useState(0);
  const [deleteCount, setDeleteCount] = React.useState({});
  const [moveToTopCount, setMoveToTopCount] = React.useState({});
  const [pauseButton, setPauseButton] = React.useState(false);
  const [playing, setPlaying] = React.useState(false);
  const [random, setRandom] = React.useState(false);
  const [lastfm, setLastfm] = React.useState(false);
  // Queued tracks recommended by Last.fm: URI -> Last.fm track page
  const [lastfmTracks, setLastfmTracks] = React.useState({});

  useEffect(() => {
    async function getTrackList() {
      const isRandom = await mopidy.tracklist.getRandom();
      setRandom(isRandom);
      if (isRandom) {
        // In random mode the play order is not exposed by Mopidy, so show
        // every other track in the tracklist. The first element is the current
        // track (or a placeholder), because Playlist renders slice(1).
        const current = await mopidy.playback.getCurrentTlTrack();
        const allTracks = await mopidy.tracklist.getTlTracks();
        const rest = allTracks.filter(t => !current || t.tlid !== current.tlid);
        setTrackList([current || {}, ...rest]);
      } else {
        const tracks = await mopidy.tracklist.slice({
              start: await mopidy.tracklist.index({}),
              end: await mopidy.tracklist.getLength()
            });
        setTrackList(tracks);
      }
    }

    async function updateTrackList(track) {
      let trackInfo = track ? getTrackInfo(track) : {};
      const streamTitle = await mopidy.playback.getStreamTitle();
      if (streamTitle) {
        const splitStreamTitle = streamTitle.split(" - ")

        trackInfo.artists = splitStreamTitle.length > 1 ? splitStreamTitle[0] : streamTitle;
        trackInfo.album = splitStreamTitle.length > 1 ? splitStreamTitle[1] : "";
      }
      setTrackInfo(trackInfo);
      await getTrackList();
    }

    mopidy.on("state:online", async () => {
      const currentState = await mopidy.playback.getState();
      setPlaying(currentState === "playing");
      const currentTrack = await mopidy.playback.getCurrentTrack();

      await updateTrackList(currentTrack);
    });
    mopidy.on("event:trackPlaybackStarted", async ({ tl_track }) => {
      await updateTrackList(tl_track.track);
      setSkipCount(0);
    });
    mopidy.on("event:tracklistChanged", async () => {
      const currentTrack = await mopidy.playback.getCurrentTrack();

      await updateTrackList(currentTrack);
      setSkipCount(0);
    });
    mopidy.on("event:streamTitleChanged", async () => {
      const currentTrack = await mopidy.playback.getCurrentTrack();
      await updateTrackList(currentTrack);
    });
    mopidy.on("event:optionsChanged", async () => {
      const currentTrack = await mopidy.playback.getCurrentTrack();
      await updateTrackList(currentTrack);
    });
    mopidy.on("event:playbackStateChanged", ({old_state, new_state}) => {
      setPlaying(new_state === "playing");
    });

    yap.onmessage = function(event) {
      const response = JSON.parse(event.data);
      if (response.action === "lastfm_update") {
        setLastfmTracks(response.payload.tracks);
        return;
      }
      setSnackbarMessage(response.payload.message);
      switch (response.action) {
        case "delete_update":
          setDeleteCount(response.payload.deletes);
          break
        case "top_update":
          setMoveToTopCount(response.payload.tops);
          break
        case "skip_update":
          setSkipCount(response.payload.votes);
          break;
        case "connect":
          setSkipCount(response.payload.votes);
          setMoveToTopCount(response.payload.tops);
          setDeleteCount(response.payload.deletes);
          setPauseButton(response.payload.pause_button);
          setLastfm(Boolean(response.payload.lastfm));
          setLastfmTracks(response.payload.lastfm_tracks || {});
          break;
        default:
          break;
      }
      setOpenSnackbar(true);
    };
  }, []);

  return (
    <React.Fragment>
      <CssBaseline enableColorScheme/>
      <div className="yap">
        <Snackbar
          open={openSnackbar}
          onClose={() => setOpenSnackbar(false)}
          anchorOrigin={{vertical: "top", horizontal: "center"}}
          slots={{transition: Fade}}
          message={snackbarMessage}
          autoHideDuration={3000}
          action={
            <IconButton
              aria-label="close"
              color="inherit"
              sx={{ p: 0.5}}
              onClick={() => setOpenSnackbar(false)}>
              <Close />
            </IconButton>
          }
        />
        <Container maxWidth="lg">
          <Grid container columnSpacing={0} rowSpacing={2} sx={{justifyContent: "center"}}>
            <Grid size="auto">
              <SkipButton onClick={() => handleSkip(trackInfo)} skipCount={skipCount}/>
              {pauseButton &&
                <Tooltip title={playing ? "Pause" : "Play"}>
                  <IconButton color="primary" size="large" onClick={() => {
                    handleTogglePlay(playing);
                    setPlaying(!playing);
                  }}>
                    {playing ? <Pause/> : <PlayArrow/>}
                  </IconButton>
                </Tooltip>
              }
            </Grid>
            <Grid size="grow"/>
            <Grid size="auto">
              <Tooltip title="Change theme">
                <IconButton size="large" onClick={colorMode.toggleColorMode} color="inherit">
                  <BrightnessMedium/>
                </IconButton>
              </Tooltip>
            </Grid>
            <Grid size={12}>
              <Playlist
                yap={yap}
                trackInfo={trackInfo}
                trackList={trackList}
                deleteCount={deleteCount}
                moveToTopCount={moveToTopCount}
                random={random}
                lastfmTracks={lastfmTracks}
              />
            </Grid>
            <SearchComponent mopidy={mopidy}/>
            {lastfm &&
              <Grid size={12}>
                <Typography variant="caption" component="p" sx={{textAlign: "center"}}>
                  Recommendations powered by{" "}
                  <Link href="https://www.last.fm" target="_blank" rel="noopener noreferrer">
                    AudioScrobbler
                  </Link>
                </Typography>
              </Grid>
            }
          </Grid>
        </Container>
      </div>
    </React.Fragment>
  );
}

export default function ToggleColorMode() {

  const prefersDarkMode = useMediaQuery('(prefers-color-scheme: dark)');

  const savedTheme = localStorage.getItem('theme');

  const initialTheme = savedTheme ? savedTheme : (prefersDarkMode ? 'dark' : 'light');

  const [mode, setMode] = React.useState(initialTheme);
  const colorMode = React.useMemo(
    () => ({
      toggleColorMode: () => {
        setMode((prevMode) => (prevMode === 'light' ? 'dark' : 'light'));
      },
    }),
    [],
  );

  const theme = React.useMemo(
    () =>
      createTheme({
        palette: {
          mode,
        },
      }),
    [mode],
  );

  localStorage.setItem('theme', mode);

  return (
    <ColorModeContext.Provider value={colorMode}>
      <ThemeProvider theme={theme}>
        <Yap />
      </ThemeProvider>
    </ColorModeContext.Provider>
  );
}

const container = document.getElementById('root');
const root = createRoot(container);
root.render(<ToggleColorMode/>);
