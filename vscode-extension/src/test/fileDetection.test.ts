import * as assert from 'assert';
import { detectVideoPath } from '../utils/fileDetection';

describe('detectVideoPath', () => {
    it('should detect Windows absolute paths', () => {
        assert.strictEqual(
            detectVideoPath('analyze C:\\Users\\demo\\video.mp4'),
            'C:\\Users\\demo\\video.mp4'
        );
    });

    it('should detect Unix absolute paths', () => {
        assert.strictEqual(
            detectVideoPath('analyze /home/user/video.mp4'),
            '/home/user/video.mp4'
        );
    });

    it('should detect quoted paths', () => {
        assert.strictEqual(
            detectVideoPath('analyze "C:\\path with spaces\\video.mp4"'),
            'C:\\path with spaces\\video.mp4'
        );
    });

    it('should detect relative paths', () => {
        const result = detectVideoPath('analyze ./videos/demo.mov');
        assert.ok(result?.endsWith('demo.mov'));
    });

    it('should return undefined for non-video files', () => {
        assert.strictEqual(detectVideoPath('analyze document.pdf'), undefined);
    });

    it('should return undefined for empty input', () => {
        assert.strictEqual(detectVideoPath(''), undefined);
    });

    it('should return undefined for text without paths', () => {
        assert.strictEqual(detectVideoPath('hello world'), undefined);
    });

    it('should detect .mkv files', () => {
        assert.ok(detectVideoPath('C:\\videos\\recording.mkv'));
    });

    it('should detect .webm files', () => {
        assert.ok(detectVideoPath('/tmp/screen.webm'));
    });

    it('should detect .avi files', () => {
        assert.ok(detectVideoPath('D:\\capture.avi'));
    });
});
