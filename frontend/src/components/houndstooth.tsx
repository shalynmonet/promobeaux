import { useRef } from "react";
import { StyleProp, View, ViewStyle } from "react-native";
import Svg, { Defs, Pattern, Rect } from "react-native-svg";

import { useTheme } from "@/src/theme";

// Classic 8x8 houndstooth tile (1 = ink), matching the Promobeaux logo's cart pattern.
const BITS = ["11110001", "11110011", "11110111", "11111111", "11100000", "11000000", "10000000", "00000000"];
const RUNS = BITS.flatMap((row, y) => {
  const runs: { x: number; y: number; w: number }[] = [];
  let start = -1;
  for (let x = 0; x <= row.length; x++) {
    if (row[x] === "1" && start < 0) start = x;
    if (row[x] !== "1" && start >= 0) {
      runs.push({ x: start, y, w: x - start });
      start = -1;
    }
  }
  return runs;
});

let seq = 0;

/** Black-and-white houndstooth band. Fills its width; by default one full pattern tile fits its height. */
export function Houndstooth({ height, cell, style, testID }: { height: number; cell?: number; style?: StyleProp<ViewStyle>; testID?: string }) {
  const { colors } = useTheme();
  const id = useRef(`hound${++seq}`).current;
  const unit = cell ?? height / 8;
  const tile = 8 * unit;
  return (
    <View style={[{ height, overflow: "hidden" }, style]} testID={testID} pointerEvents="none">
      <Svg width="100%" height={height}>
        <Defs>
          <Pattern id={id} patternUnits="userSpaceOnUse" width={tile} height={tile}>
            <Rect width={tile} height={tile} fill={colors.surfaceSecondary} />
            {RUNS.map((r, i) => (
              <Rect key={i} x={r.x * unit} y={r.y * unit} width={r.w * unit} height={unit} fill={colors.onSurface} />
            ))}
          </Pattern>
        </Defs>
        <Rect width="100%" height={height} fill={`url(#${id})`} />
      </Svg>
    </View>
  );
}
