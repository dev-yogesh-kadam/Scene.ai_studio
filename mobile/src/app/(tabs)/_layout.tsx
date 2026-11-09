import { Tabs } from 'expo-router';
import { useState } from 'react';

import { TabBar } from '@/components/TabBar';
import { WhatsNew } from '@/components/WhatsNew';
import { markSeen, toShow } from '@/lib/whatsNew';
import { colors } from '@/theme';

export default function TabsLayout() {
  // After an update, what's new shows once, over the first screen.
  const [news, setNews] = useState(toShow);
  return (
    <>
      <Tabs
        tabBar={(props) => <TabBar {...props} />}
        screenOptions={{ headerShown: false, animation: 'fade', sceneStyle: { backgroundColor: colors.background } }}>
        <Tabs.Screen name="home" options={{ title: 'Home' }} />
        <Tabs.Screen name="projects" options={{ title: 'Projects' }} />
        <Tabs.Screen name="create" options={{ title: 'Create' }} />
        <Tabs.Screen name="library" options={{ title: 'Library' }} />
        <Tabs.Screen name="skills" options={{ title: 'Skills' }} />
      </Tabs>
      <WhatsNew
        release={news}
        onClose={() => {
          markSeen();
          setNews(null);
        }}
      />
    </>
  );
}
