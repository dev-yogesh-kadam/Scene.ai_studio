// A still of a made item, for a thumbnail: an image as it is, a video as its poster, a sound or a text (a transcript, a
// list of times) as a mark and its name. The poster is a small picture the server makes from the video, so a page of
// thumbnails doesn't start loading every video. A picture of the library has one too (960 wide, made once and kept): a
// canvas of full-size pictures, each several megabytes, would load slowly. The viewer shows the picture itself. With
// the item's size the thumbnail keeps its place before it loads (width and height), so nothing below it jumps.

import { Icon } from './Icon/Icon';
import { classesOf } from '../cx';
import css0 from './Shared3.module.css';
import css1 from '../../studio/features/agent/Composer.module.css';
import css2 from '../../studio/features/agent/Markdown.module.css';
import css3 from '../../studio/features/agent/Results.module.css';
const css = classesOf(css0, css1, css2, css3);

const HAS_POSTER = /^\/api\/((admin\/)?library|kit)\/\d+\/file$/;

/** The address of a thumbnail: a library item's or a NeuralCore entry's poster instead of its file. */
export const thumbUrl = (url: string) => (HAS_POSTER.test(url) ? url.replace(/\/file$/, '/poster') : url);

type Props = { url: string; kind: string; name?: string; width?: number; height?: number };

export function Still({ url, kind, name = '', width, height }: Props) {
  if (kind === 'audio' || kind === 'text') {
    return (
      <div className={css('sound')}>
        <Icon name={kind === 'audio' ? 'audio' : 'book'} />
        <span>{name}</span>
      </div>
    );
  }
  const src = kind === 'video' ? url.replace(/\/file$/, '/poster') : thumbUrl(url);
  const size = width && height ? { width, height } : {};
  return <img src={src} alt={name} loading="lazy" decoding="async" draggable={false} {...size} />;
}
