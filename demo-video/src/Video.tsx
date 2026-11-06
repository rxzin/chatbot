import { AbsoluteFill, Sequence } from "remotion";
import { FootageScene, ProgressBar, SceneSpeed } from "./components";
import { AgentLoop, Architecture, Intro, Memory, Outro, Safeguards } from "./scenes";
import { C } from "./theme";
import type { Timeline } from "./timeline";

const SCENES = { intro: Intro, architecture: Architecture, agent: AgentLoop, memory: Memory, safeguards: Safeguards, outro: Outro };

export function Video({ timeline }: { timeline: Timeline }) {
  const { chapters, total } = timeline;
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      {chapters.map((c) => (
        <Sequence key={c.id + c.from} from={c.from} durationInFrames={c.duration} name={c.title}>
          {c.kind === "footage" ? (
            <FootageScene chapter={c} />
          ) : (
            (() => {
              const Scene = SCENES[c.id];
              return (
                <SceneSpeed.Provider value={c.speed}>
                  <Scene duration={c.duration} />
                </SceneSpeed.Provider>
              );
            })()
          )}
        </Sequence>
      ))}
      <ProgressBar chapters={chapters} total={total} />
    </AbsoluteFill>
  );
}
