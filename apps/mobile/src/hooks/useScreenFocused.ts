import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';

/** Whether this screen is the one on top, so it polls only while someone is looking at it. */
export function useScreenFocused() {
  const [focused, setFocused] = useState(false);
  useFocusEffect(
    useCallback(() => {
      setFocused(true);
      return () => setFocused(false);
    }, []),
  );
  return focused;
}
