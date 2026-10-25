import { Image } from "expo-image";
import { StyleProp, View, ViewStyle } from "react-native";

// Seamless tile cut from the Promobeaux houndstooth strip artwork (ink on sage), 55x16 at 1x.
const TILE = require("../../assets/images/houndstooth-tile.png");
const TILE_W = 55;
const TILE_H = 16;

/** Houndstooth brand band: the strip artwork repeated across the full width, one tile tall. */
export function Houndstooth({ height = TILE_H, style, testID }: { height?: number; style?: StyleProp<ViewStyle>; testID?: string }) {
  const tileW = (TILE_W * height) / TILE_H;
  // Enough tiles for the widest phone/tablet; extra tiles are clipped.
  const count = Math.ceil(1400 / tileW);
  return (
    <View style={[{ height, overflow: "hidden", flexDirection: "row" }, style]} testID={testID} pointerEvents="none">
      {Array.from({ length: count }, (_, i) => (
        <Image key={i} source={TILE} style={{ width: tileW, height }} contentFit="fill" />
      ))}
    </View>
  );
}
