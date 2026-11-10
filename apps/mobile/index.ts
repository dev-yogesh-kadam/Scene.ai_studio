// The phone site's entry: first the redirect of the libraries' <style> elements, so their CSS applies under the
// studio's Content-Security-Policy (src/lib/cspStyles.ts), then expo-router, which loads the site from src/app.
import { installStylesUnderPolicy } from './src/lib/cspStyles';

installStylesUnderPolicy();
require('expo-router/entry');
