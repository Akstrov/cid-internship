import { Component } from '@angular/core';
import { ViewerComponent } from './components/viewer/viewer.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [ViewerComponent],
  template: '<app-viewer />',
})
export class AppComponent {}
