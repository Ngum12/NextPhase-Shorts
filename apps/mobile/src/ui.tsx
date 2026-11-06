import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { colors as c } from './theme';
import { SafeAreaView } from 'react-native-safe-area-context';

export function Page({ children, safeTop = false }: { children: React.ReactNode; safeTop?: boolean }) {
  // Stack headers and the tab bar handle their own top/bottom insets.
  return <SafeAreaView edges={safeTop ? ['top', 'left', 'right'] : ['left', 'right']} style={s.page}>{children}</SafeAreaView>;
}
export function Title({ children }: { children: React.ReactNode }) {
  return <Text style={s.title}>{children}</Text>;
}
export function Body({ children }: { children: React.ReactNode }) {
  return <Text style={s.body}>{children}</Text>;
}
export function Button({ title, onPress, disabled, secondary }: { title: string; onPress: () => void; disabled?: boolean; secondary?: boolean }) {
  return <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress}
    style={({pressed}) => [s.button, secondary && s.secondary, (disabled || pressed) && {opacity:.65}]}>
    <Text style={[s.buttonText, secondary && {color: c.text}]}>{title}</Text>
  </Pressable>;
}
export function Loading() { return <View style={{padding:32}}><ActivityIndicator color={c.accent}/></View>; }
export const s = StyleSheet.create({
  page: { flex: 1, padding: 22, backgroundColor: c.bg, gap: 18 },
  title: { color: c.text, fontWeight: '800', fontSize: 29, letterSpacing: -0.7 },
  body: { color: c.muted, fontSize: 15, lineHeight: 23 },
  card: { backgroundColor: c.surface, padding: 18, borderRadius: 18, borderWidth: 1, borderColor: c.border, gap: 8 },
  cardTitle: { color: c.text, fontSize: 18, fontWeight: '700' },
  button: { backgroundColor: c.accent, borderRadius: 13, minHeight: 50, alignItems: 'center', justifyContent: 'center', paddingHorizontal:16 },
  secondary: { backgroundColor: c.surface2, borderWidth: 1, borderColor: c.border },
  buttonText: { color: '#061A18', fontWeight:'800', fontSize: 16 },
  input: { backgroundColor: c.surface, color: c.text, borderRadius: 13, borderWidth:1, borderColor:c.border, padding: 15, fontSize:16 },
});
