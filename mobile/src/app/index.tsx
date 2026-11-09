import { Redirect } from 'expo-router';

import { useSession } from '@/hooks/useSession';

export default function Index() {
  const { status } = useSession();
  return <Redirect href={status === 'signedIn' ? '/home' : '/login'} />;
}
