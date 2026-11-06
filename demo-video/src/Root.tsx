import { Composition } from "remotion";
import { FPS, HEIGHT, HIGHLIGHTS_TIMELINE, TIMELINE, WIDTH } from "./timeline";
import { Video } from "./Video";

export function Root() {
  return (
    <>
      {/* Fast highlight reel, under a minute. */}
      <Composition
        id="Highlights"
        component={Video}
        defaultProps={{ timeline: HIGHLIGHTS_TIMELINE }}
        durationInFrames={HIGHLIGHTS_TIMELINE.total}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
      />
      {/* Full walkthrough of every feature. */}
      <Composition
        id="Demo"
        component={Video}
        defaultProps={{ timeline: TIMELINE }}
        durationInFrames={TIMELINE.total}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
      />
    </>
  );
}
