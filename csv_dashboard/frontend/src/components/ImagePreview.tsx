import { imageUrl } from '../api/client';

export function ImagePreview({ images }: { images: string[] }) {
  if (!images.length) return <span className="muted">Không có ảnh</span>;

  return (
    <div className="image-grid">
      {images.map((image) => (
        <a href={imageUrl(image)} target="_blank" rel="noreferrer" key={image} className="image-thumb">
          <img src={imageUrl(image)} alt={`Ảnh minh họa ${image}`} loading="lazy" />
        </a>
      ))}
    </div>
  );
}
