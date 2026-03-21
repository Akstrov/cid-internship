// src/app/components/upload/upload.component.ts
import { Component, Output, EventEmitter, ChangeDetectorRef } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../services/api.service';

@Component({
  selector: 'app-upload',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './upload.component.html',
  styleUrls: ['./upload.component.css'],
})
export class UploadComponent {
  @Output() uploadSuccess = new EventEmitter<string>();  // emits the new pair _id

  // Form fields
  defect     = '';
  fiche      = '';
  commentary = '';
  severity   = '';
  sourcePdf  = '';

  // Image
  selectedFile   : File | null = null;
  previewUrl     : string | null = null;

  // State
  submitting = false;
  error      = '';
  success    = false;

  constructor(private api: ApiService, private cdr: ChangeDetectorRef) {}

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (!input.files?.length) return;

    const file = input.files[0];
    if (!file.type.startsWith('image/')) {
      this.error = 'Please select a JPEG or PNG image.';
      return;
    }

    this.selectedFile = file;
    this.error = '';

    // Preview
    const reader = new FileReader();
    reader.onload = () => {
      this.previewUrl = reader.result as string;
      this.cdr.detectChanges();
    };
    reader.readAsDataURL(file);
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    const file = event.dataTransfer?.files[0];
    if (!file) return;
    const fakeEvent = { target: { files: [file] } } as any;
    this.onFileSelected(fakeEvent);
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
  }

  isValid(): boolean {
    return !!this.selectedFile && !!this.defect.trim();
  }

  submit(): void {
    if (!this.isValid() || this.submitting) return;

    this.submitting = true;
    this.error      = '';
    this.success    = false;

    const fd = new FormData();
    fd.append('image',      this.selectedFile!);
    fd.append('defect',     this.defect.trim());
    fd.append('fiche',      this.fiche.trim());
    fd.append('commentary', this.commentary.trim());
    fd.append('severity',   this.severity);
    fd.append('source_pdf', this.sourcePdf.trim());

    this.api.createPair(fd).subscribe({
      next: (created: any) => {
        this.submitting = false;
        this.success    = true;
        this.reset();
        this.cdr.detectChanges();
        this.uploadSuccess.emit(created._id);
      },
      error: (err) => {
        this.submitting = false;
        this.error = err?.error?.detail || 'Upload failed. Please try again.';
        this.cdr.detectChanges();
      },
    });
  }

  reset(): void {
    this.defect      = '';
    this.fiche       = '';
    this.commentary  = '';
    this.severity    = '';
    this.sourcePdf   = '';
    this.selectedFile = null;
    this.previewUrl   = null;
  }
}
